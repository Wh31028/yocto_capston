CC ?= gcc
CFLAGS += -Wall -Wextra -O2
LDFLAGS ?=

TARGET = can_fota_flasher
SRCS = can_fota_flasher.c

all: $(TARGET)

$(TARGET): $(SRCS)
	$(CC) $(CFLAGS) $(SRCS) -o $(TARGET) $(LDFLAGS)

clean:
	rm -f $(TARGET)
