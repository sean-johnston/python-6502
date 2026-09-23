import queue
import socket
import selectors
from enum import Enum
from pathlib import Path

# File modes
class FileMode(Enum):
    # Does not listen to data port
    IDLE = 0

    # Load a filename
    FILE_NAME = 0xff
    #
    # byte 0 - Length of filename
    # byte 1 - First byte
    # ...
    # byte n - nth byte

    # Read the data
    FILE_DATA = 0xfe
    #
    # byte 0 - High byte of length of data
    # byte 1 - Low byte of length of data
    # byte 2 - First byte
    # ...
    # byte n - nth byte

    # Save the data, and go back to idle
    END_DATA = 0xfd

    # Load the data
    READ_DATA = 0Xfc

    # Load a catalog of the SD card
    CATALOG = 0xfb

    # Delete file from the SD card
    DELETE = 0xfa

file_state = FileMode.IDLE.value

# Registers in the IO
class io(Enum):
    CHROUT          = 0x1
    FILE_MODE       = 0x2
    FILE_DATA       = 0x3
    CHRIN           = 0x4
    FILE_LOAD_DATA  = 0x5
    DEBUG_IO_ENABLE = 0x6
    LCD_STATE       = 0x7
    SOUND           = 0x8

# Registers in the 6551
class io_6551(Enum):
    TX_RX           = 0x00 # ACIA transmit/receive data port
    RES_STS         = 0x01 # ACIA reset/status port
    CMD             = 0x02 # ACIA command port
    CTL             = 0x03 # ACIA control port

#in_map = {
#    "\x1b[1~":0x13,  #* HOME
#    "\x1b[2~":0x94,  #* INSERT
#    "\x1b[3~":0x7F,  #* DELETE
#    "\x1b[4~":0x93,  #* END
#    "\x1b[C" :0x1D,  #* RIGHT
#    "\x1b[D" :0x9D   #* LEFT
#}


class IO_SERVER:
    def __init__(self):
        self.mysel = selectors.DefaultSelector()
        self.server = None
        self.done = False
        self.data_queue = queue.Queue(maxsize=1024)
        self.conn = None
        self.has_connection = False

        self.filename_length = 0
        self.filename_pos = 0

        self.data_length = 0
        self.data_pos = 0
        self.first_byte = False

        self.load_data_length = 0
        self.load_data_pos = 0

        self.filename = None
        self.data = None
        self.load_data = None

        self.error_status = 0
        self.debug_io = True #False

        self.BASE_FS = "fs/data/"

        self.cnt = 0
        self.out_map = None
        self.in_map = None

        self.param_cnt       = 0
        self.params_read     = 0
        self.params          = bytearray(10)
        self.map_set         = 0             # Current map set
        self.map_set_command = False         # Map set command flag
        self.raw_output      = False
        self.mapped          = None
        self.PARAMETER       = '|'           # Character used for a parameter

        self.registers_6551  = bytearray(4)
        self.unget_values = []

    #***************************************
    #
    # Set the out_map for the keyboard
    #
    # out_map - out_map to set
    #
    #***************************************
    def set_out_map(self, out_map):
        self.out_map = out_map

    #***************************************
    #
    # Set the in_map for the keyboard
    #
    # in_map - in_map to set
    #
    #***************************************
    def set_in_map(self, in_map):
        self.in_map = {}
        cnt = 0
        # Iterate through the in_map
        for i in in_map[0]:
            # If we have a value
            if i is not None:
                # Get bytes in the slot, and 
                # generate the key
                key = ""
                for x in i:
                    if x != 0: key += chr(x)
                # Store the key and value for 
                # the in_map
                self.in_map[key] = cnt
            # Increment the count
            cnt += 1

    #***************************************
    #
    # Function that gets called when a socket
    # is accepted
    #
    # sock - socket to accept
    #
    #***************************************
    def accept_wrapper(self, sock):
        """Handles new incoming client connections."""
        conn, addr = sock.accept()  # Should be ready to accept immediately
        print(f"Accepted connection from {addr}")
        conn.setblocking(False)     # Make the client socket non-blocking
        
        # Register the client socket for read (receive) events
        self.mysel.register(conn, selectors.EVENT_READ, data=self.handle_client_data)
        self.has_connection = True

    #***************************************
    #
    # Function that gets called when a client
    # socket has data
    #
    #***************************************
    def handle_client_data(self, conn):
        """Handles reading data from existing client connections."""
        try:
            data = conn.recv(1024)  # Should be ready to read immediately
            if data:
                #print(f"Received {data!r} from client")
                #conn.sendall(data)  # Echo the data back
                for d in data:
                    if d != 0:
                        self.data_queue.put(d)
            else:
                print("Client closed connection")
                self.mysel.unregister(conn)
                conn.close()
        except ConnectionResetError:
            print("Client disconnected unexpectedly")
            self.mysel.unregister(conn)
            conn.close()

    #***************************************
    #
    # Initialize the IO server
    #
    #***************************************
    def init_server(self):
        # Setup the primary listening server socket
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('127.0.0.1', 8080))
        self.server.listen()

        # Unblock the server socket
        self.server.setblocking(False)

        # Register the server socket to listen for read (incoming connection) events
        self.mysel.register(self.server, selectors.EVENT_READ, data=self.accept_wrapper)

        print("Non-blocking server running on 127.0.0.1:8080...")

    #***************************************
    #
    # Process the sockets
    #
    #***************************************
    def server_process(self):
        # Check for socket event
        events = self.mysel.select(timeout=0.1)

        # Process socket event
        for key, mask in events:
            callback = key.data
            callback(key.fileobj)  # Execute accept_wrapper or handle_client_data

    #***************************************
    #
    # Thread that is running to processing 
    # the sockets
    #
    #***************************************
    def terminal_thread(self):
        # Initialize the server
        self.init_server()

        # While not done, continue processing the socket
        while not self.done:
            self.server_process()

        # Close the socket when we are done
        self.mysel.close()

    #***************************************
    #
    # If we have an escape character process
    # it to handle in_map data
    #
    # Returns a character based on sequence,
    # or 0 if no valid sequence
    #
    #***************************************
    def process_esc(self) -> int:
        seq: str = ""
        ch:int = 0x1b

        # Process the key input until there is not keypress
        while ch is not None: 
            seq += chr(ch)
            ch = self.get_from_queue()

            if ch == 0x1b:
                if not self.data_queue.empty():
                    self.ungetchar(ch)
                    ch = 0
                    break
        # Find the seqence in the in map
        #for x in seq:
        #    print(self.cnt, ord(x), end=None)
        #print("")
        self.cnt += 1
        if self.in_map is not None:
            if seq in self.in_map:
                return self.in_map[seq]
        # If we didn't find a mapping, return 0
        return 0

    #***************************************
    #
    # Store input character for later
    #
    #***************************************
    def ungetchar(self, ch):
        self.unget_values.append(ch)

    #***************************************
    #
    # Get a character from the input queue
    #
    #***************************************
    def get_from_queue(self) -> int:
        if len(self.unget_values) != 0:
            return self.unget_values.pop(0)

        # Get a character from the queue
        # if return the character. If the 
        # queue is empty return None
        try:
            return self.data_queue.get_nowait()
        except queue.Empty:
            return None

    #***************************************
    #
    # Check if there is a character in the
    # queue
    #
    #***************************************
    def is_character_in_queue(self) -> int:
        if len(self.unget_values) != 0:
            return True
        return not self.data_queue.empty()

    #***************************************
    #
    # Get an input character
    #
    #***************************************
    def get_char(self) -> int:
        ch = self.get_from_queue()
        if ch == 27:
            ch = self.process_esc()
        return ch

    #***************************************
    #
    # Get a sequence based on an output value
    #
    #***************************************
    def get_mapped(self, value: int) -> str:
    # If character is 0
        if value == 0:
            # Set the map set command flag
            self.map_set_command = True

            # Return mapping for getting a parameter
            return bytearray(self.PARAMETER,"utf-8")

        # Start with 0 mapping
        ch = None

        # If other set if greater than 0
        if self.map_set > 0 and self.map_set < len(self.out_map):
            ch = self.out_map[self.map_set]

        # If map set does not have a map, use the main map.
        if ch is None: ch = self.out_map[0][value]

        # Return the mapping.
        return ch

    #***************************************************
    # Get number of character in sequence
    # 
    # seq - Sequence
    #
    # Returns the number of parameters in a sequence
    #***************************************************
    def get_params(self, seq):
        # Start at zero
        param_count = 0
        cnt = 0

        # While we have character
        while cnt < len(seq) and seq[cnt] != 0:
            # If pipe character increment count
            if seq[cnt] == ord(self.PARAMETER): 
                param_count += 1
            cnt += 1
        return param_count

    #***************************************
    #
    # Translate output mapping to something
    # that can be output
    #
    #***************************************
    def translate_mapping(self, data):
        if len(data) == 1:
            #if data[0] != chr(0) and self.raw_output:
            #    return data
            value = data
            if self.param_cnt > 0:
                # Store parameter for later use
                self.params[self.params_read] = ord(value)
                self.params_read +=1

                # If we have all the parameters
                if self.params_read == self.param_cnt:

                    # If this is a map set command
                    if self.map_set_command:
                        if self.params[0] == 0xff:
                            self.raw_output = True
                        #elif self.params[0] == 0xfe:
                        #    self.raw_output = False
                        else:
                            # Set the parameter to the map set
                            if self.map_set < len(self.out_map):
                                self.map_set = self.params[0]

                        # Reset the map set command flag.
                        self.map_set_command = False
                        buf = None
                    else:
                        # Process sequence
                        #print(tuple(self.params))
                        #print(self.mapped)
                        pass
                        format = ""
                        for i in self.mapped:
                            if i != 0:
                                # If we have a pipe character (parameter)
                                if i == ord(self.PARAMETER):
                                    format += "{}"
                                else:
                                    # Added a character from the mapped sequence
                                    format += chr(i)
                        # Produce the final sequence
                        buf = format.format(*(tuple(self.params)))

                    # Reset the parameter count and mapped variables
                    self.param_cnt = 0
                    self.mapped = None
                    return buf
                else:
                    return None
            else:
                # If we have a mapped parameter
                self.mapped = self.get_mapped(ord(value))
                if self.mapped is not None:
                    # Get number of parameters
                    self.param_cnt = self.get_params(self.mapped)
                    # If there are parameter
                    if self.param_cnt > 0:
                        # Set the read count and clear the parameters
                        self.params_read = 0
                        return None
                    else:
                        # Just output the mapped character
                        out = ""
                        for ch in self.mapped:
                            if ch != 0: out += chr(ch)
                        return out
                else:
                    return value
                    #print("value:",value)
        return data

    #***************************************
    #
    # Set a string to all of the sockets
    #
    #***************************************
    def put_string(self, data):
        if self.raw_output:
            if ord(data) == 0:
                self.raw_output = False
                return

        if not self.raw_output:
            result = self.translate_mapping(data)
            if result is None: return
            data = result
        else:
            pass

        #b = bytearray(len(result))
        #for x in result:
        #    b[cnt] = ord(x)
        #    cnt += 1
        # Iterate through all the client sockets
        for key in list(self.mysel.get_map().values()):
            # Get the client socket
            client_sock = key.fileobj
            
            # Skip the main listening server socket
            if client_sock == self.server:
                continue

            try:
                # Send the complete message
                #b = bytes(data, encoding="utf-8")
                b = bytes(data, encoding="latin-1")
                client_sock.sendall(b)
            except (ConnectionResetError, BrokenPipeError):
                # Clean up disconnected clients safely during broadcast
                print(f"Client disconnected during broadcast: {client_sock.getpeername()}")
                self.mysel.unregister(client_sock)
                client_sock.close()        #sel = list(self.mysel.get_map().values())

    #***************************************
    #
    # Send a character out
    #
    #***************************************
    def chrout(self, value):
        self.put_string(chr(value))

    #***************************************
    #
    # Get a character in
    #
    #***************************************
    def chrin(self):
        d = self.get_char()
        if d is None: return 0
        return d

    #***************************************
    #
    # Get a character from the loaded data
    #
    #***************************************
    def file_load_data(self):
        # If there is some data
        if self.load_data is not None:

            # Get new byte
            load_ch = self.load_data[self.load_data_pos]

            # Increment the position
            self.load_data_pos +=1

            # If we run out of data, free the data buffer, and set an error.
            if self.load_data_pos >= self.load_data_length + 2:
                # free data
                self.load_data = None
                self.load_data_pos = 0
                self.load_data_length = 0

                # Return 0
                load_ch = 0

                # Set error
                self.error_status = 3

            # Return the byte
            return load_ch 
        else:
            #DISPLAY_DEBUG("++++\n")
            # If we don't have any more data, return 0
            return 0

    #***************************************
    #
    # Display debug output
    #
    #***************************************
    def DISPLAY_DEBUG(self, data, no_cr=False):
        if self.debug_io:
            if no_cr:
                print(data, end="")
            else:
                print(data)


    #***************************************
    #
    # Scan directory from data directory.
    # If a directory path is specified, 
    # get the directory from that path
    #
    #***************************************
    def scan_files(self, path):
        # Initialize the buffer
        data = bytearray(2)
        data[0] = 0
        data[1] = 0

        # Open the directory

        dir_path = Path(path)
        for item in dir_path.iterdir():
            if item.is_dir():
                tmp = f"<DIR>  {item.name}\r\n"
            else:
                tmp = f"{item.stat().st_size:<6} {item.name}\r\n"

            # Append it to the end of the buffer
            data.extend(tmp.encode('utf-8'))

        # Store file size at the start of the buffer, with high byte first
        data[1] = len(data)-2 & 0xff
        data[0] = len(data)-2 >> 8

        # Return the data
        return data

    #***************************************
    #
    # Clean up all the buffers
    #
    #***************************************
    def cleanup_buffers(self):
        # Clean up the buffers
        self.filename = None
        self.data = None
        self.load_data = None
        self.load_data_pos = 0
        self.first_byte = False

    #***************************************
    #
    # Set the file mode, and execute code
    # based on the specified mode
    #
    #***************************************
    def file_mode(self, value):
        self.DISPLAY_DEBUG(f"File mode: {value}")
        self.file_state = value
        # We are done, Save the file and reset the buffers.
        if self.file_state == FileMode.END_DATA.value:
            # If we don't have a file name
            if self.filename is None:
                self.DISPLAY_DEBUG("No file name")

            # Send the file to the sd card
            else:
                #filename[filename_pos] = 0
                self.DISPLAY_DEBUG(f"Filename: {self.filename}")

            # No data
            if self.data is None:
                self.DISPLAY_DEBUG("No data")
            else:
                # Zero terminate the buffer
                #data[data_pos] = 0
                self.DISPLAY_DEBUG(f"Data: self.data")


            if not Path(self.BASE_FS).exists():
                self.DISPLAY_DEBUG("ERROR: Could not mount filesystem")
                self.error_status = 5
                return 0

            # If there is a file name
            if self.filename is not None:
                # Prepend the data directory on the file
                new_filename  = self.BASE_FS
                replace = 0
                if self.filename[0] == '@':
                    replace = 1
                    new_filename += self.filename[1:]
                else:
                    new_filename += self.filename

                # Make the directory is it does not exist

                dir, delimiter, tail = new_filename.rpartition('/')

                dir_path = Path(dir)

                # Create the directory safely
                dir_path.mkdir(parents=True, exist_ok=True)

                # If we are not replacing the file
                if not replace:
                    # Check if it exists
                    file_path = Path(new_filename)

                    if file_path.is_file():
                        error_status = 6
                        return 0

                # Open file for writing
                try:
                    with open(new_filename, "wb") as file:
                        # Write the data buffer to the file
                        file.write(self.data) #data_pos

                except OSError as e:
                    self.DISPLAY_DEBUG("ERROR: Could not open file (%d)")
                    error_status = 1
                    return 0

            self.cleanup_buffers()
            self.load_data_pos = 0
            self.file_state = 0
            self.first_byte = False

        # If 0, force to idle mode
        if self.file_state == FileMode.IDLE.value:
            self.error_status = 0
            self.cleanup_buffers()


        # Delete a file
        if self.file_state == FileMode.DELETE.value:
            # If no file
            if self.filename is None:
                self.DISPLAY_DEBUG("No file name")
            else:
                self.DISPLAY_DEBUG(f"Filename: {self.filename}")

            if not Path(self.BASE_FS).exists():
                self.DISPLAY_DEBUG("ERROR: Could not mount filesystem")
                self.error_status = 5
                return 0

            # If we have a file name
            if self.filename is not None:
                # Prepend data directory to file name
                new_filename = self.BASE_FS
                new_filename += self.filename
                self.DISPLAY_DEBUG(f"Filename: {new_filename}")


                file_path = Path(new_filename)

                try:
                    # missing_ok=True ignores FileNotFoundError if it's already gone
                    file_path.unlink(missing_ok=True)
                    self.error_status = 0
                except PermissionError:
                    self.error_status = 6
                except IsADirectoryError:
                    self.error_status = 6
            else:
                self.error_status = 4

            # Clean up
            self.cleanup_buffers()

        if self.file_state == FileMode.READ_DATA.value:
            # No file name
            if self.filename is None:
                self.DISPLAY_DEBUG("No file name")
            else:
                # Terminate filename buffer with zero
                self.DISPLAY_DEBUG(f"Filename: {self.filename}")

            if not Path(self.BASE_FS).exists():
                self.DISPLAY_DEBUG("ERROR: Could not mount filesystem")
                self.error_status = 5
                return 0

            if self.filename is not None:
                # Prepend data directory to filename
                new_filename = self.BASE_FS
                new_filename += self.filename
                self.DISPLAY_DEBUG(f"Filename: {new_filename}")

                # Open file for Reading
                try:
                    with open(new_filename, "rb") as file:
                        # Read the file into the data buffer
                        self.data = file.read()
                        self.load_data_length = len(self.data)
                        # Store the length at the beginning of the buffer, hight byte first

                        self.load_data = bytearray(self.load_data_length + 2)
                        self.load_data[1] = self.load_data_length & 0xff
                        self.load_data[0] = self.load_data_length >> 8

                        cnt = 2
                        for d in self.data:
                            self.load_data[cnt] = d
                            cnt += 1

                    pass

                    for d in self.data:
                        ld_chr = d
                        self.DISPLAY_DEBUG(f"{ld_chr:02x} ", True)
                    self.DISPLAY_DEBUG("")

                except OSError as e:
                    self.DISPLAY_DEBUG("ERROR: Could not open file ({new_filename})")
                    self.error_status = 1
                    return 0
            else:
                self.error_status = 4

        if self.file_state == FileMode.CATALOG.value:
            dir_path = Path(self.BASE_FS)
            if not dir_path.is_dir():
                self.DISPLAY_DEBUG("ERROR: Could not mount filesystem")
                self.error_status = 5
                return 0

            else:
                # Read the files on SD card, and return a buffer, with
                # the list
                new_filename = self.BASE_FS
                if self.filename is not None:
                    new_filename += self.filename
                self.DISPLAY_DEBUG(f"\nFilename: {self.filename}")
                self.DISPLAY_DEBUG(f"\nFile Path: {new_filename}")
                x = self.scan_files(new_filename)
                self.DISPLAY_DEBUG(x[2:])
                if self.load_data is not None:
                    self.load_data = None
                    self.load_data_pos = 0

                self.load_data = x
                self.load_data_length = (self.load_data[0] << 0x08) | (self.load_data[1] & 0xff)
                print(self.load_data[0])
                print(self.load_data[1])
                pass

    #***************************************
    #
    # Function that set file data
    #
    #***************************************
    def file_data(self, value):
        self.DISPLAY_DEBUG(f"File data: {value} - File mode: {self.file_state}")

        # If sending the filename
        if self.file_state == FileMode.FILE_NAME.value:
            if self.filename is None:
                # If filename does not exist, allocate it
                self.filename_length = value 
                self.filename = ""
                self.filename_pos = 0
            else:
                # Fill in the filename until we have reached the size.
                if self.filename_pos != self.filename_length:
                    self.filename += chr(value)
                    self.filename_pos +=1

        # If sending the data
        if self.file_state == FileMode.FILE_DATA.value:
            if self.data is None:
                # If we do not has a data buffer, get the first byte
                # of the length if it is not set, if it is get the second 
                # byte of the length.
                if not self.first_byte:
                    self.data_length = value << 8
                    self.first_byte = True
                else:
                    # If we have the first byte, get the second byte and
                    # allocate the data buffer.
                    self.data_length = self.data_length | value
                    self.data = bytearray(self.data_length)
                    self.data_pos = 0
            else:
                # Fill in the data buffer until we have reached the size.
                if self.data_pos != self.data_length:

                    # Todo: fix?
                    self.data[self.data_pos] = value
                    ############
                    self.data_pos +=1


    #***************************************
    #
    # Process the IO based on the register
    # (index) in the IO
    #
    # block - Block object referenced
    # addr  - Addressing to access
    # index - Index within the block to access
    # value - Value to write, if read flag is False
    # read  - Read flag. True if reading. False if writing
    #
    #***************************************
    def process_io(self, block, addr, index, value, read):
        # Send character to output
        if read == False:
            if index == io.CHROUT.value: 
                self.chrout(value) # Write to output

            if index == io.FILE_MODE.value:
                self.file_mode(value)

            if index == io.FILE_DATA.value:
                self.file_data(value)

            # Enable debug. Any non-zero value
            if index == io.DEBUG_IO_ENABLE.value:
                self.DEBUG_IO = value

        else:
            #Get character from input
            if index == io.CHRIN.value:
                return self.chrin() # Read from input
            # Load the next byte of data
            if index == io.FILE_LOAD_DATA.value: 
                return self.file_load_data()
            # Return the status of data
            if index == io.FILE_DATA.value:
                self.DISPLAY_DEBUG(f"Error status: {self.error_status}")
                return self.error_status

        # Return if the LCD is installed or not
        if index == io.LCD_STATE.value:
            return 0 # LCD is not installed, for now
        #    return config.lcd_installed

        return 0

    #***************************************
    #
    # Process the 6551 based on the register
    # (index) in the IO
    #
    # block - Block object referenced (Not used)
    # addr  - Addressing to access (Not used)
    # index - Index within the block to access
    # value - Value to write, if read flag is False
    # read  - Read flag. True if reading. False if writing
    #
    #***************************************
    def process_6551(self, block, addr, index, value, read):
        # Send character to output
        if read == False:
            self.registers_6551[index] = value 
            if index == io_6551.TX_RX.value:
                #if value == 0 and not self.is_character_in_queue():
                #    pass
                #else:
                self.chrout(value) # Write to output

            if index == io_6551.RES_STS.value: # Doesn't matter
                pass

            if index == io_6551.CMD.value: # Doesn't matter
                pass

            if index == io_6551.CTL.value: # Doesn't matter
                pass
        else:
            #Get character from input
            if index == io_6551.TX_RX.value: 
                r = self.chrin()
                return  r # Read from input

            if index == io_6551.RES_STS.value:
                r = (0x10 | 0x08) if self.is_character_in_queue() else 0x10
                return r

            if index == io_6551.CMD.value:
                return self.registers_6551[index]

            if index == io_6551.CTL.value:
                return self.registers_6551[index]

        return 0
