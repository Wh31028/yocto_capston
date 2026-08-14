CC ?= gcc
CFLAGS ?= -Wall -Wextra -O2
CPPFLAGS ?= -D_DEFAULT_SOURCE -D_POSIX_C_SOURCE=200809L
LDFLAGS ?=

TARGET = can_fota_flasher
SRCS = main.c can_socket.c fota_common.c custom_fota.c isotp_fota.c
OBJS = $(SRCS:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(OBJS)

%.o: %.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(OBJS)
