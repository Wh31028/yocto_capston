TARGET = can_fota_flasher
FLASHER_DIR = flasher

all: $(TARGET)

$(TARGET): $(FLASHER_DIR)/$(TARGET)
	cp $< $@

$(FLASHER_DIR)/$(TARGET):
	$(MAKE) -C $(FLASHER_DIR)

clean:
	rm -f $(TARGET)
	$(MAKE) -C $(FLASHER_DIR) clean
