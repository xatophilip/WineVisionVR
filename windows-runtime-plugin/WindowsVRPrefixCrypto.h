#pragma once
// One-time pre-server repair for old win64 templates which never registered
// stock i386 RSAEnh. Values mirror pinned Wine dlls/rsaenh/rsaenh.rgs;
// the contract also compares them to genuine guest32 DllRegisterServer output.
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef __APPLE__
#include <copyfile.h>
#endif

namespace WVRPrefixCrypto {
enum class Result { Added, Existing, Error };
constexpr size_t MaxHiveBytes = 16 * 1024 * 1024;
struct FD {
    int value;
    explicit FD(int v = -1) : value(v) {}
    ~FD() { if (value >= 0) close(value); }
    FD(const FD &) = delete;
    FD &operator=(const FD &) = delete;
};
// Open the caller-trusted app container or signed resource base directly.
// iOS can grant this path without permitting opens of /private or /var.
inline int OpenRoot(const std::string &path) {
    if (path.empty() || path[0] != '/') return -1;
    return open(path.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
}
inline int Walk(int root, const std::string &relative) {
    if (relative.empty() || relative[0] == '/') return -1;
    int current = fcntl(root, F_DUPFD_CLOEXEC, 0);
    for (size_t at = 0; current >= 0 && at < relative.size();) {
        size_t end = relative.find('/', at);
        if (end == std::string::npos) end = relative.size();
        std::string part = relative.substr(at, end - at);
        at = end + 1;
        if (part.empty() || part == "." || part == "..") { close(current); return -1; }
        int next = openat(current, part.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        close(current); current = next;
    }
    return current;
}
inline bool UTF8(const std::string &s) {
    for (size_t i = 0; i < s.size();) {
        uint32_t c = static_cast<unsigned char>(s[i++]);
        if (!c) return false;
        if (c < 128) continue;
        unsigned more;
        uint32_t minimum;
        if (c >= 0xc2 && c <= 0xdf) { more = 1; minimum = 0x80; c &= 31; }
        else if (c >= 0xe0 && c <= 0xef) { more = 2; minimum = 0x800; c &= 15; }
        else if (c >= 0xf0 && c <= 0xf4) { more = 3; minimum = 0x10000; c &= 7; }
        else return false;
        if (more > s.size() - i) return false;
        while (more--) {
            unsigned char next = s[i++];
            if ((next & 0xc0) != 0x80) return false;
            c = (c << 6) | (next & 63);
        }
        if (c < minimum || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff)) return false;
    }
    return true;
}
inline int Hex(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
// Decode the same C/hex/octal escapes as Wine server/unicode.c parse_strW.
// Non-ASCII characters cannot alias the ASCII subtree name.
inline bool Key(const std::string &line, size_t at, std::string &key) {
    while (at < line.size()) {
        unsigned value = static_cast<unsigned char>(line[at++]);
        if (value == ']') return true;
        if (value == '\\') {
            if (at == line.size()) return false;
            value = static_cast<unsigned char>(line[at++]);
            if (value == 'x') {
                value = 'x';
                if (at < line.size() && Hex(line[at]) >= 0) {
                    value = 0;
                    for (unsigned n = 0; n < 4 && at < line.size() && Hex(line[at]) >= 0; ++n)
                        value = value * 16 + Hex(line[at++]);
                }
            } else if (value >= '0' && value <= '7') {
                value -= '0';
                for (unsigned n = 0; n < 2 && at < line.size() && line[at] >= '0' && line[at] <= '7'; ++n)
                    value = value * 8 + line[at++] - '0';
            } else {
                const char *escapes = "abefnrtv";
                const char *found = std::strchr(escapes, value);
                const unsigned translated[] = {7, 8, 27, 12, 10, 13, 9, 11};
                if (found) value = translated[found - escapes];
            }
        }
        if (!value) return false;
        if (value >= 'A' && value <= 'Z') value += 'a' - 'A';
        key += value < 128 ? static_cast<char>(value) : static_cast<char>(0x80);
    }
    return false;
}
inline bool Inspect(const std::string &text, bool &existing) {
    existing = false;
    if (!UTF8(text)) return false;
    size_t first = text.find('\n');
    std::string header = text.substr(0, first);
    if (!header.empty() && header.back() == '\r') header.pop_back();
    if (header != "WINE REGISTRY Version 2") return false;
    bool win64 = false;
    const std::string target = "software\\wow6432node\\microsoft\\cryptography\\defaults";
    for (size_t at = 0; at < text.size();) {
        size_t end = text.find('\n', at);
        if (end == std::string::npos) end = text.size();
        std::string line = text.substr(at, end - at);
        at = end + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.compare(0, 6, "#arch=") == 0) {
            if (line != "#arch=win64") return false;
            win64 = true;
        }
        size_t start = line.find_first_not_of(" \t");
        if (start != std::string::npos && line[start] == '[') {
            std::string key;
            if (!Key(line, start + 1, key)) return false;
            if (key == target || (key.size() > target.size() &&
                key.compare(0, target.size(), target) == 0 && key[target.size()] == '\\'))
                existing = true;
        }
    }
    return win64;
}
inline std::string StockAppend() {
    const std::string base = R"(Software\\Wow6432Node\\Microsoft\\Cryptography\\Defaults)";
    std::string text = "\n\n;; WineVision stock i386 RSAEnh defaults; existing hive bytes preserved.\n";
    struct Provider { const char *name; unsigned type; };
    const Provider providers[] = {
        {"Microsoft Base Cryptographic Provider v1.0", 1},
        {"Microsoft Enhanced Cryptographic Provider v1.0", 1},
        {"Microsoft Enhanced RSA and AES Cryptographic Provider", 24},
        {"Microsoft Enhanced RSA and AES Cryptographic Provider (Prototype)", 24},
        {"Microsoft RSA SChannel Cryptographic Provider", 12},
        {"Microsoft Strong Cryptographic Provider", 1},
    };
    for (const auto &provider : providers) {
        char type[40]; std::snprintf(type, sizeof(type), "\"Type\"=dword:%08x\n\n", provider.type);
        text += "[" + base + R"(\\Provider\\)" + provider.name + "]\n";
        text += R"("Image Path"="C:\\windows\\system32\\rsaenh.dll")" "\n";
        text += "\"Signature\"=hex:de,ad,be,ef\n";
        text += type;
    }
    struct Type { const char *number; const char *name; const char *description; };
    const Type types[] = {
        {"001", "Microsoft Enhanced Cryptographic Provider v1.0", "RSA Full (Signature and Key Exchange)"},
        {"012", "Microsoft RSA SChannel Cryptographic Provider", "RSA SChannel"},
        {"024", "Microsoft Enhanced RSA and AES Cryptographic Provider", "RSA Full and AES"},
    };
    for (const auto &type : types) {
        text += "[" + base + R"(\\Provider Types\\Type )" + type.number + "]\n";
        text += "\"Name\"=\"" + std::string(type.name) + "\"\n";
        text += "\"TypeName\"=\"" + std::string(type.description) + "\"\n\n";
    }
    return text;
}
inline bool SameFile(const struct stat &a, const struct stat &b) {
    return a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_size == b.st_size &&
        a.st_mode == b.st_mode && a.st_uid == b.st_uid && a.st_gid == b.st_gid &&
        a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec &&
        a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec;
}
inline bool Read(int fd, size_t count, std::string &data) {
    data.assign(count, '\0');
    size_t at = 0;
    while (at < count) {
        ssize_t got = pread(fd, data.data() + at, count - at, static_cast<off_t>(at));
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) return false;
        at += static_cast<size_t>(got);
    }
    return true;
}
inline bool TrustedI386Provider(const std::string &resourceRoot) {
    FD root(OpenRoot(resourceRoot));
    if (root.value < 0) return false;
    FD parent(Walk(root.value, "Runtime/i386-windows"));
    if (parent.value < 0) return false;
    FD file(openat(parent.value, "rsaenh.dll", O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
    if (file.value < 0) return false;
    struct stat info{};
    if (fstat(file.value, &info) || !S_ISREG(info.st_mode) || info.st_size < 88 || info.st_size > 8 * 1024 * 1024)
        return false;
    std::string data;
    if (!Read(file.value, static_cast<size_t>(info.st_size), data)) return false;
    auto u16 = [&](size_t at) { return static_cast<unsigned char>(data[at]) |
        (static_cast<unsigned char>(data[at + 1]) << 8); };
    auto u32 = [&](size_t at) { return static_cast<uint32_t>(u16(at)) | (static_cast<uint32_t>(u16(at + 2)) << 16); };
    if (data[0] != 'M' || data[1] != 'Z') return false;
    size_t pe = u32(60);
    return pe <= data.size() - 26 && data.compare(pe, 4, "PE\0\0", 4) == 0 &&
        u16(pe + 4) == 0x014c && (u16(pe + 22) & 0x2000) &&
        u16(pe + 20) >= 96 && static_cast<size_t>(u16(pe + 20)) <= data.size() - pe - 24 &&
        u16(pe + 24) == 0x010b;
}
inline Result Ensure(const std::string &documents, const std::string &relativePrefix,
                     const std::string &resources, std::string &error) {
    auto fail = [&](const char *why) { error = why; return Result::Error; };
    FD root(OpenRoot(documents));
    if (root.value < 0) return fail("The app container is not a safe directory.");
    FD directory(Walk(root.value, relativePrefix));
    if (directory.value < 0) return fail("The Wine prefix path is not a safe directory.");
    FD hive(openat(directory.value, "system.reg", O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
    struct stat original{};
    if (hive.value < 0 || fstat(hive.value, &original) || !S_ISREG(original.st_mode) ||
        original.st_nlink != 1 || original.st_uid != geteuid() || original.st_size < 0 ||
        static_cast<uint64_t>(original.st_size) > MaxHiveBytes ||
        flock(hive.value, LOCK_EX | LOCK_NB) != 0)
        return fail("The Wine registry cannot be safely checked for 32-bit crypto defaults.");
    std::string before;
    bool existing = false;
    if (!Read(hive.value, static_cast<size_t>(original.st_size), before) || !Inspect(before, existing))
        return fail("The Wine registry format is not safe for the 32-bit crypto migration.");
    if (existing) return Result::Existing;
    if (!TrustedI386Provider(resources))
        return fail("The bundled 32-bit stock crypto provider is missing or invalid.");
    const std::string append = StockAppend();
    if (append.size() > MaxHiveBytes - before.size())
        return fail("The Wine registry is too large for a bounded crypto migration.");
    const std::string after = before + append;
    static std::atomic<unsigned> sequence{};
    std::string temporary;
    FD output;
    for (unsigned tries = 0; tries != 16; ++tries) {
        temporary = ".system.reg.wvr-crypto-" + std::to_string(getpid()) + "-" +
            std::to_string(sequence.fetch_add(1));
        output.value = openat(directory.value, temporary.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
        if (output.value >= 0 || errno != EEXIST) break;
    }
    if (output.value < 0) return fail("Cannot create the atomic Wine registry migration.");
    struct Temporary {
        int directory; const std::string &name; bool committed = false;
        ~Temporary() { if (!committed) unlinkat(directory, name.c_str(), 0); }
    } cleanup{directory.value, temporary};
#ifdef __APPLE__
    if (fcopyfile(hive.value, output.value, nullptr, COPYFILE_METADATA) != 0)
        return fail("Cannot preserve Wine registry metadata.");
#endif
    if (fchmod(output.value, original.st_mode & 0777) != 0)
        return fail("Cannot preserve Wine registry permissions.");
    size_t at = 0;
    while (at < after.size()) {
        ssize_t written = write(output.value, after.data() + at, after.size() - at);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) return fail("Cannot write the atomic Wine registry migration.");
        at += static_cast<size_t>(written);
    }
    if (fsync(output.value) != 0) return fail("Cannot flush the atomic Wine registry migration.");
    struct stat current{}, opened{};
    std::string currentBytes;
    if (fstatat(directory.value, "system.reg", &current, AT_SYMLINK_NOFOLLOW) ||
        fstat(hive.value, &opened) || !SameFile(original, current) || !SameFile(original, opened) ||
        !Read(hive.value, before.size(), currentBytes) || currentBytes != before)
        return fail("The Wine registry changed while preparing its crypto migration.");
    if (renameat(directory.value, temporary.c_str(), directory.value, "system.reg") != 0)
        return fail("Cannot publish the atomic Wine registry migration.");
    cleanup.committed = true;
    // The rename is already committed; failure to sync directory metadata must
    // not report that the original file is still in place.
    (void)fsync(directory.value);
    return Result::Added;
}
} // namespace WVRPrefixCrypto
