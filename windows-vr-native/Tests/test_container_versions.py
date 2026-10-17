#!/usr/bin/env python3
"""Execute the real bounded container adapter under ASan/UBSan on macOS.

Uses deliberately synthetic raw BC bytes to verify container transport exactly;
this does not establish that any shader compiles on a headset.
"""
from pathlib import Path
import argparse, json, subprocess
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[2];build=a.build.resolve();build.mkdir(parents=True,exist_ok=True)
source=(root/'windows-vr-native/Sources/WindowsVRMetalDiagnostics.mm').read_text()
def function(signature):
 start=source.index(signature);brace=source.index('{',start);end=brace+1;depth=1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
helpers='\n'.join(function(x)for x in ['static uint16_t Read16(', 'static uint64_t Read64(', 'static void Write16(', 'static void Write32(', 'static void Write64('])
adapter=function('static dispatch_data_t CorrectContainerVersions(')
new_guard='(Read16(bytes + 12) != 1 && Read16(bytes + 12) != 2)'
assert adapter.count(new_guard)==1
old_adapter=adapter.replace('CorrectContainerVersions(','OriginalCorrectContainerVersions(',1).replace(new_guard,'Read16(bytes + 12) != 1')
code=r'''
#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <array>
'''+helpers+'\n'+adapter+'\n'+old_adapter+r'''
static void putTag(std::vector<uint8_t>&v,const char*tag,const std::vector<uint8_t>&payload){v.insert(v.end(),tag,tag+4);v.push_back(payload.size()&255);v.push_back((payload.size()>>8)&255);v.insert(v.end(),payload.begin(),payload.end());}
struct Fixture{std::vector<uint8_t>bytes;size_t versionOffset,hashOffset,sizeOffset,bitcodeOffset;};
static Fixture fixture(uint16_t os){
 Fixture f;std::vector<uint8_t>section(8);Write32(section.data(),1);putTag(section,"NAME",{'t','e','s','t','_','v','s',0});
 f.versionOffset=88+section.size();std::vector<uint8_t>vers(8);Write16(vers.data(),2);Write16(vers.data()+2,6);Write16(vers.data()+4,3);Write16(vers.data()+6,1);putTag(section,"VERS",vers);
 f.hashOffset=88+section.size()+6;putTag(section,"HASH",std::vector<uint8_t>(32));f.sizeOffset=88+section.size()+6;std::vector<uint8_t>length(8);Write64(length.data(),12);putTag(section,"MDSZ",length);section.insert(section.end(),{'E','N','D','T'});
 f.bitcodeOffset=88+section.size();f.bytes.resize(f.bitcodeOffset+12);auto*b=f.bytes.data();memcpy(b,"MTLB",4);Write16(b+4,1);Write16(b+6,2);Write16(b+8,7);b[11]=0x8b;Write16(b+12,os);Write64(b+16,f.bytes.size());Write64(b+24,88);Write64(b+32,section.size());Write64(b+72,f.bitcodeOffset);Write64(b+80,12);memcpy(b+88,section.data(),section.size());const uint8_t raw[]={0x42,0x43,0xc0,0xde,1,2,3,4,5,6,7,8};memcpy(b+f.bitcodeOffset,raw,12);return f;
}
static dispatch_data_t makeDispatchData(const std::vector<uint8_t>&b){return dispatch_data_create(b.data(),b.size(),nullptr,DISPATCH_DATA_DESTRUCTOR_DEFAULT);}
static std::vector<uint8_t> bytes(dispatch_data_t d){const void*p=nullptr;size_t size=0;dispatch_data_t m=dispatch_data_create_map(d,&p,&size);assert(m);return std::vector<uint8_t>((const uint8_t*)p,(const uint8_t*)p+size);}
static void unchanged(std::vector<uint8_t>b){auto input=makeDispatchData(b);auto output=CorrectContainerVersions(input);assert(output==input&&bytes(output)==b);}
int main(){@autoreleasepool{
 const auto one=fixture(1),two=fixture(2);
 auto modernOriginal=bytes(OriginalCorrectContainerVersions(makeDispatchData(one.bytes)));auto modernCurrent=bytes(CorrectContainerVersions(makeDispatchData(one.bytes)));assert(modernOriginal==modernCurrent);
 // This failing control demonstrates why the local xros2 container was missed.
 auto legacyInput=makeDispatchData(two.bytes);assert(OriginalCorrectContainerVersions(legacyInput)==legacyInput);
 const auto fixed=bytes(CorrectContainerVersions(legacyInput));assert(fixed!=two.bytes&&fixed==modernCurrent);
 assert(Read64(fixed.data()+16)==fixed.size());const size_t wrapped=32;assert(Read64(fixed.data()+80)==wrapped&&Read64(fixed.data()+two.sizeOffset)==wrapped);assert(fixed.size()==two.bitcodeOffset+wrapped);
 const uint8_t*w=fixed.data()+two.bitcodeOffset;assert(w[0]==0xde&&w[1]==0xc0&&w[2]==0x17&&w[3]==0x0b);assert(w[8]==20&&w[12]==12);for(unsigned i=16;i<20;i++)assert(w[i]==255);
 assert(memcmp(w+20,two.bytes.data()+two.bitcodeOffset,12)==0);assert(Read16(fixed.data()+12)==2);assert(Read16(fixed.data()+two.versionOffset+8)==7&&Read16(fixed.data()+two.versionOffset+12)==2);
 uint8_t digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(w,wrapped,digest);assert(memcmp(digest,fixed.data()+two.hashOffset,sizeof digest)==0);
 // Every unrelated header/section byte remains unchanged except documented fields.
 std::vector<bool>changed(two.bitcodeOffset,false);for(auto range:std::array<std::pair<size_t,size_t>,6>{{{12,2},{16,8},{80,8},{two.sizeOffset,8},{two.hashOffset,32},{two.versionOffset+8,6}}})for(size_t i=range.first;i<range.first+range.second;i++)changed[i]=true;
 for(size_t i=0;i<two.bitcodeOffset;i++)if(!changed[i])assert(fixed[i]==two.bytes[i]);
 unchanged(fixed); // An already wrapped library is never double wrapped.
 for(uint16_t os:{0,3,27,65535})unchanged(fixture(os).bytes);
 auto b=two.bytes;b[11]=0x81;unchanged(b);b=two.bytes;Write16(b.data()+4,0x8001);unchanged(b);b=two.bytes;Write16(b.data()+8,8);unchanged(b);b=two.bytes;Write32(b.data()+88,2);unchanged(b);
 for(size_t field:{size_t(16),size_t(24),size_t(32),size_t(72),size_t(80)})for(uint64_t value:{uint64_t(0),uint64_t(0xffffffffffffffffULL),uint64_t(two.bytes.size()+1)}){b=two.bytes;Write64(b.data()+field,value);unchanged(b);}
 for(size_t field:{two.versionOffset,two.hashOffset-6,two.sizeOffset-6}){b=two.bytes;memcpy(b.data()+field,"NOPE",4);unchanged(b);}
 b=two.bytes;Write16(b.data()+two.versionOffset+8,5);unchanged(b);b=two.bytes;Write16(b.data()+two.versionOffset+4,65535);unchanged(b);
 unchanged(std::vector<uint8_t>());unchanged(std::vector<uint8_t>(95));unchanged(std::vector<uint8_t>(8*1024*1024+1));
 printf("PASS: actual xros1/xros2 adapter preserves raw IR and all unrelated bytes, writes valid wrapper lengths/hash/versions, matches original xros1 output, and leaves wrapped/unknown/malformed inputs unchanged (ASan/UBSan)\n");
 }}
'''
cpp=build/'test.mm';exe=build/'test';cpp.write_text(code)
subprocess.run(['xcrun','--sdk','macosx','clang++','-std=c++20','-O1','-g','-fobjc-arc','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-framework','Foundation','-o',str(exe)],check=True)
result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30);(build/'test.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
(build/'result.json').write_text(json.dumps({'actualProductionAdapter':True,'xros1OutputMatchesOriginal':True,'xros2PreviouslyMissedControl':True,'rawIRUnchanged':True,'wrapperSizeAndSHA256':'passed','unknownWrappedMalformedPassthrough':'passed','sanitizers':'ASan/UBSan passed','scope':'Synthetic container transport only; no shader compilation or headset execution'},indent=2)+'\n');print(result.stdout.strip())
