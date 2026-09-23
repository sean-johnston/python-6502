#!/usr/bin/env python
# -*- coding: utf-8 -*-
from cpu import CPU
from mmu import MMU
import threading
#import time
from io_server import IO_SERVER
#from configure import Attr
#from configure import IO_EMULATION
#from configure import FLOW_CONTROL
from configure import config        

class emu():
    def __init__(self):
        self.io_server = IO_SERVER()
        self.io_thread = threading.Thread(target=self.io_server.terminal_thread, args=())
        self.io_thread.start()
        self.configuration : dict = None
        self.COMMENT       : str  = "*"
        self.BASE_FS       : str  = "fs"
        self.line_lookup   : dict = {}
        self.menu_items    : str  = "123456789ABCDEFGHIJKLMNOPQRSTUVWYZ"


    #***************************************
    #
    # Wait for connection before proceeding,
    # so we can start outputting to the 
    # terminal
    #
    #***************************************
    def wait_for_connection(self):
        print("Waiting for connection")
        while self.io_server.has_connection == False:
            pass
        print("Connected")

    #***************************************
    #
    # Prompts the user on the terminal to
    # press ENTER. Waits for the user to
    # and then returns from the function
    #
    #***************************************
    def enter_to_start(self):
        self.io_server.put_string("Press ENTER to continue")
        x = self.io_server.get_char()
        while x != 13:
            x = self.io_server.get_char()
        self.io_server.put_string("\r\n")

    #***************************************
    #
    # Load the configuration file, and store
    # the maps on the IO server, to be used
    # when mapping character and keystrokes
    #
    #***************************************
    def load_configuration(self, config_file):
        c = config()
        c.read_config(config_file)        
        self.configuration = c.config_data
        self.io_server.set_out_map(c.config_data["OUT_MAP"])
        self.io_server.set_in_map(c.config_data["IN_MAP"])

    #***************************************
    #
    # Load the menu of the roms. Allows the 
    # user to select from the menu, and 
    # returns the rom and other information.
    #
    # config - Pointer to the configuration
    #          structure
    # start  - Pointer to an unsigned short
    #          integer of the start address
    #          of the ROM.
    # length - Pointer to an unsigned short
    #          integer of the length of the
    #          ROM.
    #  
    # via    - Pointer to an unsigned short
    #          integer of the via address.
    #
    # io     - Pointer to an unsigned short
    #          integer of the I/O address.
    #
    # Returns the binary of the ROM, or 
    # NULL if a rom was not able to be
    # loaded.
    #
    #***************************************
    def get_menu_options(self):
        menu_option = None
        buf = ""

        # Open file for reading
        fn = self.BASE_FS+"/"+self.configuration["roms_txt"]
        try:
            with open(fn, "r") as file:
                if file.closed:
                    print("Could not open configuration file. Using defaults.")
                    return menu_option

                roms = []

                # Read the roms.txt file.
                count = 0

                # Get file line by line
                while (buf := file.readline()) != "":
                    buf =  buf.replace("\r\n", "").replace("\n", "").replace("\r", "").strip()

                    # If not comment or empty line
                    if len(buf) > 0 and buf[0] != self.COMMENT:
                        # Add ROM to the list
                        roms.append(buf)
                        count += 1
                        if count == len(self.menu_items): break
        except FileNotFoundError:
            print("Could not open configuration file. Using defaults.")
            return menu_option

        # Output menu
        count = 0
        for rom in roms:
            p = rom.split(",")
            self.io_server.put_string(f"{self.menu_items[count]} - {p[0]}\r\n")
            count += 1

        # Select menu option
        self.io_server.put_string("Select from the menu: \r\n")

        #i = 0;
        # Get a valid key based on the menu
        while True:
            x = self.io_server.get_char()
            while x is None:
                x = self.io_server.get_char()
            if chr(x).upper() in self.menu_items:
                pos = self.menu_items.find(chr(x).upper())
                if pos != -1:
                    rom = roms[pos]
                    break

        rom_data = rom.split(',')

        menu_option = {}

        menu_option["title"] = rom_data[0].strip()
        menu_option["file" ] = rom_data[1].strip()
        if rom_data[2][0].strip() == "$":
            menu_option["start"] = int(rom_data[2][1:].strip(), 16)
        else:
            menu_option["start"] = int(rom_data[2].strip())

        if rom_data[3][0].strip() == "$":
            menu_option["via"  ] = int(rom_data[3][1:].strip(), 16)
        else:
            menu_option["via"  ] = int(rom_data[3].strip())

        rom_data[4] = rom_data[4].strip()
        io = rom_data[4].split(":")
        if io[0][0].strip() == "$":
            menu_option["io"  ] = int(io[0][1:].strip(), 16)
        else:
            menu_option["io"  ] = int(io[0].strip())
        if len(io) > 1:
            if io[1][0].strip() == "$":
                menu_option["io_6551"  ] = int(io[1][1:].strip(), 16)
            else:
                menu_option["io_6551"  ] = int(io[1].strip())
        else:
            menu_option["io_6551"] = menu_option["io"] + 0x10

        if len(rom_data) > 5:
            menu_option["rom_readonly"] = True
        else:
            menu_option["rom_readonly"] = False

        # Return a pointer to the ROM data
        return menu_option


    #***************************************
    #
    # Load the menu of the config-list.txt. 
    # Allows the user to select from the menu, 
    # and returns the configuration file.
    # 
    # If the config-list.txt is not found,
    # config.txt is returned.
    #
    # Returns the name of the configuration
    # file selected, or config.txt.
    #
    #***************************************
    def get_config_menu(self):
        buf=""

        config_file = ""

        fn = self.BASE_FS+"/config-list.txt"

        try:
            with open(fn, "r") as file:
                if file.closed:
                    print("Could not open file config-list.txt. Using config.txt.")
                    return "config.txt"

                configs = []

                # Read the roms.txt file.
                count = 0

                # Get file line by line
                while (buf := file.readline()) != "":
                    buf =  buf.replace("\r\n", "").replace("\n", "").replace("\r", "").strip()

                    # If not comment or empty line
                    if len(buf) > 0 and buf[0] != self.COMMENT:
                        # Add ROM to the list
                        configs.append(buf)
                        count += 1
                        if count == len(self.menu_items): break
        except FileNotFoundError:
            print("Could not open file config-list.txt. Using config.txt.")
            return "config.txt"

        # Output menu
        count = 0
        for config in configs:
            p = config.split(",")
            self.io_server.put_string(f"{self.menu_items[count]} - {p[0]}\r\n")
            count += 1

        # Select menu option
        self.io_server.put_string("Select from the menu: \r\n")

        #i = 0;
        # Get a valid key based on the menu
        while True:
            x = self.io_server.get_char()
            while x is None:
                x = self.io_server.get_char()
            if chr(x).upper() in self.menu_items:
                pos = self.menu_items.find(chr(x).upper())
                if pos != -1 and pos < len(configs):
                    config = configs[pos]
                    break

        config_data = config.split(',')
        if len(config_data) > 1:
            config_file = config_data[1]
        else:
            config_file = "config.txt"

        # Return a pointer to the ROM data
        return config_file

    #***************************************
    #
    # Open the ROM file, and load it into
    # memory. setup the memory and put the
    # ROM file in memory. Attach the memory
    # to the CPU and reset it
    #
    #***************************************
    def start_emulator(self, rom_name, rom_start, io_location, io_6551, rom_readonly):
        # Open the ROM file
        opened = False
        try:
            with open(f"{self.BASE_FS}/{rom_name}", "rb") as f:
                opened = not f.closed
                # If it is opened, open the file and and get it size
                if opened:
                    data = list(f.read())
                    file_size = f.tell()  # Get current cursor position
        except FileNotFoundError:
            pass

        if opened:
            # Setup the memory and load the ROM file
            memory_layout = []
            if io_location != 0:
                memory_layout.append((io_location, 0x10, False, None, 0, self.io_server.process_io)) # registers for I/O

            memory_layout.append((io_6551, 0x04, False, None, 0, self.io_server.process_6551)) # registers for 6551
            memory_layout.append((rom_start, file_size, rom_readonly, data, 0, "ROM")) # Create ROM starting at rom_start with your program.
            memory_layout.append((0x00, 0xffff)) # Create RAM with 64k bytes

            mmu = MMU(memory_layout)

            # Attach the memory to the CPU, using vectors to run program.
            self.c = CPU(mmu, None)

            # Reset the CPU
            self.c.reset()

    def load_disassembly(self):
        """
        with open(f"out.txt", "r") as file:
            if not file.closed:
                lines = [line.strip() for line in file if line.strip()]
                for i in lines:
                    x = i.split("\t")
                    loc = x[0]
                    line = x[1]
                    #print(loc,line)
                    self.line_lookup[loc] = loc+" "+line
                #for key, value in line_lookup.items():
                #    print(f"Key: {key}, Value: {value}")
                #print(line_lookup)
            else:
                print("Could not open disassembly file.")
        """
        pass

    def run_emulator(self):
        #ips = 0
        #start_time = time.perf_counter()
        #instruction_cnt = 0
        try:
            #with open("opcodes.txt", "w") as file_opcodes:

                # While the io server is still running
                while not self.io_server.done:
                    #if self.c.r.pc == 0xf074:
                    #    return
                    #if self.c.r.pc == 0x901b:
                    #    pass
                    #print(f"{instruction_cnt}: {self.c.r.pc:04X}  - ", end = "")
                    #if f"{self.c.r.pc:04X}" in self.line_lookup:
                    #    print(self.line_lookup[f"{self.c.r.pc:04X}"])
                        #file_opcodes.write(self.line_lookup[f"{self.c.r.pc:04X}"])
                        #file_opcodes.write("\n")
                    #else:
                    #    print("---------")
                        #file_opcodes.write("---------\n")
                    #instruction_cnt += 1
                    #if self.c.r.pc >= 0x8000 and self.c.r.pc <= 0x840:
                    #    pass

                    # Step to the next instruction
                    self.c.step()
                    #ips += 1
                    #end_time = time.perf_counter()
                    #elapsed_time = end_time - start_time
                    #if int(elapsed_time) == 1:
                    #    print(ips)
                    #    start_time = time.perf_counter()
                    #    ips = 0
                    #print(c.r.pc)
                    #time.sleep(.1)

        except KeyboardInterrupt:
            # Tell the io server to stop, if control-c is pressed
            self.io_server.done = True
            print("Server shutting down.")

        # Tell the io server to stop and wait for the thread to end
        self.io_server.done = True
        self.io_thread.join()

def main():
    # Get an instance of the emulator
    emu_obj = emu()

    # Wait for the a connection to the socket
    emu_obj.wait_for_connection()

    # Prompt to press ENTER to start
    emu_obj.enter_to_start()

    config_value = emu_obj.get_config_menu()
    print(config_value)

    # Load the configuration
    emu_obj.load_configuration(config_value)

    # Display the menu and get the options
    menu_option = emu_obj.get_menu_options()
    print(menu_option)
    if menu_option is not None:
        emu_obj.load_disassembly()

        # Start the emulator
        emu_obj.start_emulator(menu_option["file"], menu_option["start"], menu_option["io"],menu_option["io_6551"],menu_option["rom_readonly"])

        # Run the emulator until it ends
        emu_obj.run_emulator()
    else:
        # Could not load the ROM file
        print("ROM file is not valid!")
if __name__ == "__main__":
    main()

