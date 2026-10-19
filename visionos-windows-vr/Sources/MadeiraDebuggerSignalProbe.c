// Explicit fresh-process diagnostic only. Never run after Wine installs signals.
#include <signal.h>
#include <pthread.h>
#include <time.h>
#include <errno.h>

static volatile sig_atomic_t delivered;
static void probe_handler(int signal_number) {
    if (signal_number == SIGUSR1) delivered |= 1;
    if (signal_number == SIGUSR2) delivered |= 2;
}
int wvr_debugger_signal_probe_eligible(void) {
    struct sigaction action;
    sigset_t mask;
    if (pthread_sigmask(SIG_SETMASK, NULL, &mask)) return 0;
    const int signals[] = {SIGUSR1, SIGUSR2};
    for (unsigned i = 0; i < 2; ++i) {
        if (sigismember(&mask, signals[i]) != 0 || sigaction(signals[i], NULL, &action)) return 0;
        if (action.sa_handler != SIG_DFL && action.sa_handler != SIG_IGN) return 0;
    }
    return 1;
}
int wvr_debugger_signal_probe_run(void) {
    if (!wvr_debugger_signal_probe_eligible()) return 1;
    const int signals[] = {SIGUSR1, SIGUSR2};
    struct sigaction saved[2], action = {0};
    sigset_t saved_mask;
    if (pthread_sigmask(SIG_SETMASK, NULL, &saved_mask)) return 2;
    action.sa_handler = probe_handler;
    sigemptyset(&action.sa_mask);
    sigaddset(&action.sa_mask, SIGUSR1);
    sigaddset(&action.sa_mask, SIGUSR2);
    if (sigaction(signals[0], NULL, &saved[0]) || sigaction(signals[1], NULL, &saved[1])) return 2;
    delivered = 0;
    if (sigaction(signals[0], &action, NULL)) return 2;
    if (sigaction(signals[1], &action, NULL)) {
        // No probe signal has been sent, so restoring the first action is safe.
        sigaction(signals[0], &saved[0], NULL);
        return 2;
    }
    for (unsigned i = 0; i < 2; ++i) {
        if (pthread_kill(pthread_self(), signals[i])) return 3;
        const struct timespec tick = {0, 10000000};
        for (unsigned attempt = 0; attempt < 200 && !(delivered & (1 << i)); ++attempt)
            nanosleep(&tick, NULL);
        // A debugger may still hold the signal. Keep benign handlers installed;
        // caller must abort launch and require a fresh process on this failure.
        if (!(delivered & (1 << i))) return 4;
    }
    if (sigaction(signals[0], &saved[0], NULL) || sigaction(signals[1], &saved[1], NULL) ||
        pthread_sigmask(SIG_SETMASK, &saved_mask, NULL)) return 5;
    return 0;
}
