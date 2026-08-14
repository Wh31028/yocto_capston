#include "protocol.h"
#include "can_socket.h"
#include "custom_fota.h"
#include "isotp_fota.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char *argv[]) {
    setbuf(stdout, NULL);
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <protocol> <firmware_path> [interface_name]\n", argv[0]);
        fprintf(stderr, "Protocols: custom, isotp\n");
        return 1;
    }

    const char *protocol = argv[1];
    const char *firmware_path = argv[2];
    const char *interface_name = (argc >= 4) ? argv[3] : "can0";

    /* Read Firmware File */
    FILE *f = fopen(firmware_path, "rb");
    if (!f) {
        fprintf(stderr, "Error opening firmware file: %s\n", firmware_path);
        return 1;
    }

    fseek(f, 0, SEEK_END);
    long fw_size_long = ftell(f);
    if (fw_size_long <= 0) {
        fprintf(stderr, "Invalid or empty firmware file: %s\n", firmware_path);
        fclose(f);
        return 1;
    }
    size_t fw_size = (size_t)fw_size_long;
    fseek(f, 0, SEEK_SET);

    uint8_t *fw_data = malloc(fw_size);
    if (!fw_data) {
        fprintf(stderr, "Failed to allocate memory for firmware (%zu bytes)\n", fw_size);
        fclose(f);
        return 1;
    }

    if (fread(fw_data, 1, fw_size, f) != fw_size) {
        fprintf(stderr, "Error reading firmware file\n");
        free(fw_data);
        fclose(f);
        return 1;
    }
    fclose(f);

    /* Initialize SocketCAN */
    int sock = open_can_socket(interface_name);
    if (sock < 0) {
        perror("Error opening/binding SocketCAN socket");
        free(fw_data);
        return 1;
    }

    /* Execute Protocol */
    int result = -1;
    if (strcmp(protocol, "custom") == 0) {
        result = start_custom_fota(sock, fw_data, fw_size);
    } else if (strcmp(protocol, "isotp") == 0) {
        result = start_isotp_fota(sock, fw_data, fw_size);
    } else {
        fprintf(stderr, "Unknown protocol: %s (Must be 'custom' or 'isotp')\n", protocol);
    }

    close(sock);
    free(fw_data);

    return (result == 0) ? 0 : 1;
}
