/* Local SITL transport adapter: disable Nagle on accepted TCP sockets.
 * Loaded only into the Hakoniwa service; no dynamics or controller changes. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <stdio.h>

static int configure(int fd) {
    if (fd >= 0) {
        int one = 1;
        if (setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one)) == 0)
            fprintf(stderr, "SITL transport: TCP_NODELAY enabled on fd %d\n", fd);
    }
    return fd;
}
int accept(int fd, struct sockaddr *addr, socklen_t *len) {
    int (*real_accept)(int, struct sockaddr *, socklen_t *) = dlsym(RTLD_NEXT, "accept");
    return configure(real_accept(fd, addr, len));
}
int accept4(int fd, struct sockaddr *addr, socklen_t *len, int flags) {
    int (*real_accept4)(int, struct sockaddr *, socklen_t *, int) = dlsym(RTLD_NEXT, "accept4");
    return configure(real_accept4(fd, addr, len, flags));
}
