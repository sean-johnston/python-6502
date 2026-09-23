from enum import Enum
from typing import TextIO
import copy

class Attr(Enum):
    NORMAL        = 0   # Normal lookup. Whole key
    FIND_STARTING = 1   # Key starts with the specified key value
    FIND_NEXT     = 2   # Get the next key starting with the specified key value

class IO_EMULATION(Enum):
    AUTO       = 0      # Auto detected. Tries to initialize the I/O
    NONE       = 1      # Do not use the I/O emulation
    FULL_PICO  = 2      # Full VIA emulation with Pico pins (Future)
    BASIC_PICO = 3      # Basic port emulation with Pico pins
    FULL_EXP   = 4      # Full VIA emulation with I/O board (Future)
    BASIC_EXP  = 5      # Basic port emulation with I/O board

class FLOW_CONTROL(Enum):
    AUTO       = 0      # Auto detected. If GPIO3 is grounded, use XON/XOFF
    NONE       = 1      # Force No flow control
    RTS_CTS    = 2      # Force RTS/CTS flow control
    XON_XOFF   = 3      # Force XON/XOFF flow control

class config():
    def __init__(self):
        self.MAP_SETS = 10

        self.COMMENT    = '*'           # Character used for a comment
        self.PARAMETER  = '|'           # Character used for a parameter
        self.ESCAPE     = '^'           # Character user for escape

        self.defines    = {}

        self.BASE_FS = "fs"
        self.tmp_file = "tmp_file.txt";
        self.output_code = True
        self.if_level = 0
        self.hide_level = 0
        self.else_count = 0
        self.config_data = None

    #***************************************
    #
    # Output to console.
    #
    # str - String to output
    #
    #***************************************
    def output_print(self, str : str):
        print(str)

    #***************************************
    #
    # Remove the line ends and trim the string
    # from both sides
    #
    # line - String to process
    #
    # Return the trimmed string
    #
    #***************************************
    def remove_line_end_and_trim(self, line) -> str:
        return line.replace("\r\n", "").replace("\n", "").replace("\r", "").strip()

    #***************************************
    #
    # Get an attribute from the file.
    #
    # file - File pointer
    # key - Key to the attribute to get
    # def - Default value if a key is not found
    # flags - Flags for the call. Valid values are:
    #     * Attr.NORMAL.value        - Searches for the exact key
    #     * Attr.FIND_STARTING.value - Find the first key that 
    #                                  the start of the key
    #     * Attr.FIND_NEXT.value     - Gets the next key that match
    #                                  the start of the key
    # last_key - Last key found
    #
    # Returns a pointer to the buffer and the last_key
    #
    #***************************************
    def get_attr(self, file: TextIO, key: str, default: str, flags: int, last_key: str) -> tuple[str, str]: 

        # If not find next
        if not flags & Attr.FIND_NEXT.value:
            # Go to start of the file
            file.seek(0)
        else:
            pass
            #flags |= ATTR_FIND_NEXT;

        found = False;

        # Get each line
        buf = file.readline()
        while buf:

            # Trim off line ending and leading a trailing spaces
            buf = buf.replace("\r\n", "").replace("\n", "").replace("\r", "").strip()

            # Ignore comments and empty lines
            if buf != "" and buf[0] != self.COMMENT:

                # split the line between the =
                p = buf.split("=")

                p_key = p[0].strip()
                if len(p) > 1:
                    p_value = p[1].strip()

                    p = p_value.split("*")
                    p_value = p[0].strip()
                else:
                    p_value = ""

                # Copy the key to the last key, so it can be returned
                if last_key is not None:
                    last_key = p_key
                    #strcpy(last_key, p_key);

                # If we are starting with the first key
                if (flags & Attr.FIND_STARTING.value) or (flags & Attr.FIND_NEXT.value):
                    # If the key is found
                    if p_key.startswith(key):
                        # Store it in the buffer, set found flag
                        # break out of the loop
                        buf = p_value
                        found = True
                        break
                else:
                    if p_key == key:
                        buf =  p_value
                        found = True;
                        break

                # Free the line, key and value
                if found == True: break
            buf = file.readline()

        # If not found copy the default
        if not found:
            buf = default
        return buf, last_key

    def utf8_encode(self, utf):
        out = bytearray(5)
        if utf <= 0x7F:
            # Plain ASCII
            out[0] = utf
            out[1] = 0
            return 1, out
        else:
            if utf <= 0x07FF:
                # 2-byte unicode
                out[0] = (((utf >> 6) & 0x1F) | 0xC0)
                out[1] = (((utf >> 0) & 0x3F) | 0x80)
                out[2] = 0
                return 2, out
            else:
                if utf <= 0xFFFF:
                    # 3-byte unicode
                    out[0] = (((utf >> 12) & 0x0F) | 0xE0)
                    out[1] = (((utf >>  6) & 0x3F) | 0x80)
                    out[2] = (((utf >>  0) & 0x3F) | 0x80)
                    out[3] = 0
                    return 3, out
                else:
                    if utf <= 0x10FFFF:
                        # 4-byte unicode
                        out[0] = (((utf >> 18) & 0x07) | 0xF0)
                        out[1] = (((utf >> 12) & 0x3F) | 0x80)
                        out[2] = (((utf >>  6) & 0x3F) | 0x80)
                        out[3] = (((utf >>  0) & 0x3F) | 0x80)
                        out[4] = 0
                        return 4, out
                    else:
                        # error - use replacement character
                        out[0] = 0xEF
                        out[1] = 0xBF
                        out[2] = 0xBD
                        out[3] = 0
                        return 3, out

    #***************************************
    #
    # Load the character mappings from the configuration file
    #
    # file - File pointer
    # mkey - Key for the map we are reading
    # show_output - Show the output as the map is populated
    #
    # Returns a populated map
    # 
    #***************************************
    def load_map(self, file: TextIO, mkey:str, show_output: bool) -> list[dict]:
        map = {}
        for i in range(0,self.MAP_SETS):
            map[i]=[None] * 256

        key = ""

        # Load key mappings
        data, key = self.get_attr(file, mkey, "", Attr.FIND_STARTING.value, key)


        # If we have data
        while data != "":
            mapping = bytearray(50)
            # Show output if the flag is set
            if show_output == True:
                self.output_print(f"Key: {key} - Data: {data}")

            cnt = 0
            x = data

            # If it is unicode
            if data[0] == 'U' or data[0] == 'u':
                # Convert number from a hex number
                num = int(data[1:], 16)
                # Translate the UTF-8
                cnt, result = self.utf8_encode(num)
    #            for (int i = 0; i < cnt; i++) {
    #                printf("%02X ", result[i], result[i]);
    #            }
    #            printf("\n");
                rcnt = 0
                for r in result:
                    mapping[rcnt] = r
                    rcnt += 1
                
    #            for (int i = 0; i < 8; i++) {
    #                printf("%02X ", mapping[i]);
    #            }
    #            printf("\n");
            # If it is an ANSI escape sequence
            else:
                d = [ord(char) for char in data]
                d.append(0)
                if d[0] == ord(self.ESCAPE):
                    cnt = 0
                    d[0] = 0x1b
                    while d[cnt] != 0:
                        # If we found an escape
                        if d[cnt] == ord(self.ESCAPE):
                            # Make it escape
                            mapping[cnt]=0x1b
                        else:
                            # Any other character
                            mapping[cnt]=d[cnt]
                        # Increment counter
                        cnt+=1
                    # Terminate mapping
                    mapping[cnt] = 0
                else:
                    # If it is a comma delimited list
                    # Get array of tokens
                    list_p = x.split(",")
                    cnt = 0

                    # While we have tokens
                    for p in list_p:
                        # Copy the key and trim
                        map_key = p.strip()

                        # If token ends in dollar sign
                        if map_key[0] == '$':
                            # Process as a hex
                            ch = int(map_key[1:], 16)
                        else:
                            # Process as decimal
                            ch = int(map_key)
                        # Store the value in the mapping
                        mapping[cnt] = ch

                        # Increment counter
                        cnt +=1

            mp = mapping

            # Get the mapping set
            map_set = 0

            # Check if there is a colon
            ms = key.split(":") #strstr(key,":")

            # If we have one, use the map set
            if len(ms) > 1:
                m = ms[1]

                # Get set value as hex
                if m[1] == '$':
                    map_set = int(m[1:],16)
                # Get set value as decimal
                else:
                    map_set = int(m)

            # If key ends in dollar sign
            num = 0
            skey = key.split("$")
            pass
            # Process key as hex
            if len(skey) > 1:
                num = int(skey[1], 16)

            # Process key as decimal
            else:
                num = int(skey[0])

            pass
            if map_set < self.MAP_SETS:
                # Store the mapping in the configuration
                map[map_set][num] = copy.deepcopy(mp)

            # Get the next key
            data, key = self.get_attr(file, mkey, "", Attr.FIND_NEXT.value, key)
        return map

    #***************************************
    #
    # Add a define to the list
    #
    # key - Key for the define
    # value - Value for the define
    # 
    #***************************************
    def add_define(self, key: str, value: str):
        self.defines[key] = value

    #***************************************
    #
    # Find the define in the list, and
    # returns the value of the key.
    #
    # p_key = Key to find
    # 
    # Returns value of the key, or None if it
    # is not found.
    #
    #***************************************
    def find_define(self, p_key : str) -> str:
        # Find the key
        if p_key in self.defines:
            return self.defines[p_key]

        # Return None if we don't find one
        return None

    #***************************************
    #
    # Read the configuration file, and 
    # return store the configuration in 
    # the dict object config_data. 
    #
    # config_data_file = File to read
    # 
    # Returns 0 for success, and non-zero
    # for an error.
    #
    #***************************************
    def read_config(self, config_data_file: str) -> int:
        self.config_data = {}
        result = 0

        # Set defaults
        self.config_data["roms_txt"]      = "roms.txt"
        self.config_data["serial_flow"]   = 0
        self.config_data["io_emulation"]  = 0
        self.config_data["lcd_installed"] = 0
        self.config_data["pico_pins"]     = 0x0000

        try:
            with open(self.BASE_FS+"/tmp_file.txt", "w") as out_fp:
                if not out_fp.closed:
                    # Include the main file
                    result = self.include_a_file(out_fp, config_data_file)
                    # If error return the result
                    if result != 0: return result
                else:
                    self.output_print(f"Build temporary file failed")
                    return 3
        except FileNotFoundError:
            self.output_print(f"Build temporary file failed")
            return 3


        # Free the defines
        self.defines = {}

        # Open file for reading
        try:
            with open(f"{self.BASE_FS}/{self.tmp_file}", "r") as file:
                if not file.closed:
                    pass
                else:
                    print("Could not open configuration file. Using defaults.")
                    return 1

                data = None;

                # Get the flag to show output from the configuration
                data, _ = self.get_attr(file,"SHOW_OUTPUT","0",Attr.NORMAL.value,None);
                self.config_data["SHOW_OUTPUT"] = True if data == "1" else False

                # Get the ROMs file name
                data, _ = self.get_attr(file,"ROM-FILE","roms.txt",Attr.NORMAL.value,None);
                self.config_data["ROMS_TXT"] = data
                if self.config_data["SHOW_OUTPUT"] == True:
                    self.output_print(f"ROM File: {data}")

                # Get flow control mode
                data, _ = self.get_attr(file,"SERIAL-FLOW","0",Attr.NORMAL.value,None)
                self.config_data["SERIAL-FLOW"] = True if data == "1" else False
                if self.config_data["SHOW_OUTPUT"] == True:
                    self.output_print(f"SERIAL-FLOW: {data}")

                # Get if LCD is installed
                data, _ = self.get_attr(file,"LCD-INSTALLED","0",Attr.NORMAL.value,None)
                self.config_data["LCD-INSTALLED"] = True if data == "1" else False
                if self.config_data["SHOW_OUTPUT"] == True:
                    self.output_print(f"LCD-INSTALLED: {data}")

                data, _ = self.get_attr(file,"SOUND1-PIN","28",Attr.NORMAL.value,None)
                self.config_data["SOUND1-PIN"] = int(data)
                if self.config_data["SHOW_OUTPUT"] == True:
                    self.output_print(f"SOUND1-PIN: {data}")
                data , _ = self.get_attr(file,"SOUND2-PIN","27",Attr.NORMAL.value,None)
                self.config_data["SOUND2-PIN"] = int(data)
                if self.config_data["SHOW_OUTPUT"] == True:
                    self.output_print(f"SOUND2-PIN: {data}")
                data , _ = self.get_attr(file,"SOUND3-PIN","26",Attr.NORMAL.value,None)
                self.config_data["SOUND2-PIN"] = int(data)
                if self.config_data["SHOW_OUTPUT"] == True:
                    self.output_print(f"SOUND3-PIN: {data}")

                # Get the I/O emulation mode
                data , _ = self.get_attr(file,"IO-EMULATION","0",Attr.NORMAL.value,None);
                if self.config_data["SHOW_OUTPUT"] == True:
                    self.output_print(f"IO-EMULATION: {data}")
                self.config_data["IO-EMULATION"] = int(data);

                # If emulation uses Pico pins
                if self.config_data["IO-EMULATION"] == IO_EMULATION.FULL_PICO.value or self.config_data["IO-EMULATION"] == IO_EMULATION.BASIC_PICO.value:
                    pass
                    count = 0

                    # Iterate through the GPIO pins
                    #for (int i = 0; i < 29; i++) {

                    #    # Get GPIO pin
                    #    sprintf(gpio, "GPIO-%i", i);
                    #    data , _ = self.get_attr(file,gpio,"RESERVED",Attr.NORMAL.value,None);

                    #    # If it is VIA
                    #    if (strcmp(data, "VIA") == 0) {
                    #        # Setup tht pin and assign it to a port and number

                    #        if (count < 8) {
                    #            # Port A
                    #            sprintf(via, "PA%i", count);
                    #        }
                    #        else {
                    #            # Port B
                    #            sprintf(via, "PB%i", count-8);
                    #        }
                    #        self.output_print(f"%s: %s\r\n", gpio, via);

                    #        # Increment the count
                    #        count++;

                # Read character mappings
                if self.config_data["SHOW_OUTPUT"] == True:
                    self.output_print(f"Loading Key Map");

                self.config_data["OUT_MAP"] = self.load_map(file, "OUT_MAP_", self.config_data["SHOW_OUTPUT"]);

                self.config_data["IN_MAP"] = self.load_map(file, "IN_MAP_", self.config_data["SHOW_OUTPUT"]);
        except FileNotFoundError:
                    print("Could not open configuration file. Using defaults.")
                    return 1
        return 0

    #***************************************
    #
    # Include a file into the out file
    #
    # out_fp - File pointer for output file
    # file   - Name of the file to include.
    #
    # Return 0 for success, and non-zero for
    # error.
    #
    #***************************************
    def include_a_file(self, out_fp: TextIO, filename: str) -> int:
        result = 0
        self.output_print(f"Opening configuration file: {filename}")
        fn = self.BASE_FS + "/" + filename

        try:
            with open(fn, "r") as in_fp:
                if in_fp.closed:
                    self.output_print(f"Could not open file: {filename}")
                    result = 1
                else:
                    buf = in_fp.readline()
                    while buf != "":

                        # Remove line end
                        buf = self.remove_line_end_and_trim(buf)

                        #***********************************************************
                        # Process substitution
                        #***********************************************************
                        while (key_index := buf.find("${")) != -1:
                            # Get replace string
                            key = buf[key_index+2:]
                            # Find the terminating curly bracket 
                            key_end_index = key.find("}")
                            # Remove curly bracket from key
                            if key_end_index != -1:
                                key = key[:key_end_index]

                            key_value = None
                            if key in self.defines:
                                key_value = self.defines[key]

                            # If we find a define, replace it
                            if key_value is not None:
                                print("${"+key+"}")
                                print(buf)
                                buf = buf.replace("${"+key+"}", key_value)
                            # If not, replace it with an empty string
                            else:
                                buf = buf.replace("${"+key+"}", "")

                        if buf == "": 
                            buf = in_fp.readline()
                            continue
                        #***********************************************************
                        # Process directive
                        #***********************************************************
                        if buf[0] == '!':

                            # Process include
                            if buf.startswith("!INCLUDE("):
                                # Get the name of the file to include
                                include_file = buf[9:]
                                # Remove trailing parentheses
                                if include_file[-1] == ')':
                                    include_file = include_file[:-1]
                                #printf("Include: %s\n", include_file)

                                # Include the file
                                self.include_a_file(out_fp, include_file)
                            elif buf.startswith("!DEFINE("):
                                # Get the define key and value
                                p = define_value = buf[8:].split(",")

                                # Get the key
                                p_key = p[0]
                                p_key = p_key.strip()

                                # Get the value
                                if len(p) > 1:
                                    p = p[1].split(")")
                                    p_value = p[0]
                                    p_value = p_value.strip()
                                else:
                                    p_value = ""

                                # Add the define
                                self.add_define(p_key, p_value)

                            elif buf.startswith("!IFDEF("):
                                # If we are outputting code
                                if self.output_code:
                                    # Get the key
                                    value = buf[7:]
                                    p = value.split(")")
                                    p_key = p[0].strip()

                                    # Find the key
                                    key = self.find_define(p_key)

                                    # If key is found, set flag to output code
                                    if key is not None:
                                        self.output_code = True

                                    # If key is not found, set flag to not output code
                                    else:
                                        self.output_code = False
                                        self.hide_level = self.if_level + 1

                                # Increment the if level
                                self.if_level += 1
                            elif buf.startswith("!IFNDEF("):
                                # If we are outputting code
                                if self.output_code:
                                    # Get the key
                                    value = buf[8:]
                                    p = value.split(")")
                                    p_key = p[0].strip()

                                    # Find the key
                                    key = self.find_define(p_key)
                                    # If key is found, set flag to not output code
                                    if key is not None:
                                        self.output_code = False
                                        self.hide_level = self.if_level + 1
                                    # If key is not found, set flag to output code
                                    else:
                                        self.output_code = True

                                # Increment the if level
                                self.if_level += 1
                            elif buf.startswith("!IFEQ("):
                                # If we are outputting code
                                if self.output_code:
                                    # Get the if value
                                    value = buf[6:]

                                    # Get the key
                                    p = value.split(",")
                                    p_key = p[0].strip()

                                    # Get the value
                                    if len(p) > 1:
                                        p = p[1].split(")")
                                        p_value = p[0].strip()
                                    else:
                                        p_value = ""

                                    # Find the key
                                    key_value = self.find_define(p_key)
                                    # If the key is found and matches the value
                                    if key_value is not None and key_value == p_value:
                                        # Turn on output flag
                                        self.output_code = True
                                    # If the key is not found or doesn't matche the value
                                    else:
                                        # Turn off output flag
                                        self.output_code = False
                                        #self.hide_level = self.if_level + 1
                                # Increment the if level
                                self.hide_level = self.if_level + 1
                                self.if_level += 1
                            elif buf.startswith("!IFNE("):
                                # If we are outputting code
                                if self.output_code:
                                    # Get the if value
                                    value = buf[6:]

                                    # Get the key
                                    p = value.split(",")
                                    p_key = p[0].strip()

                                    # Get the value
                                    if len(p) > 1:
                                        p = p[1].split(")")
                                        p_value = p[0].strip()
                                    else:
                                        p_value = ""

                                    # Find the key
                                    key_value = self.find_define(p_key)

                                    # If the key is found and does not matche the value
                                    if key_value is not None and key_value != p_value:
                                        # Turn on the output flag
                                        self.output_code = True
                                    else:
                                        # Turn off the output flag
                                        self.output_code = False
                                        self.hide_level = self.if_level + 1
                                # Increment the if level
                                self.if_level += 1
                            elif buf.startswith("!ELSE"):
                                # If the output flag is off and we are as the 
                                # if level that it was turn on, turn it on
                                if self.output_code == False and self.hide_level == self.if_level:
                                    self.output_code = True
                                # If the output flag is on and we are as the 
                                # if level that it was turn off, turn it on
                                elif self.output_code == True and self.hide_level == self.if_level:
                                    self.hide_level = self.if_level
                                    self.output_code = False
                            elif buf.startswith("!ENDIF"):
                                # If the output flag is off and we are as the 
                                # if level that it was turn on, turn it on
                                if self.output_code == False and self.hide_level == self.if_level:
                                    self.output_code = True
                                # Decrement the if level
                                self.if_level -= 1
                            else:
                                # We found an invalid directive
                                self.output_print(f"Invalid directive {buf}")
                        else:
                            if self.output_code:
                                # If normal text, output the line
                                #printf("%s\n",buf)
                                out_fp.write(f"{buf}\n")
                        buf = in_fp.readline()

        except FileNotFoundError:
            self.output_print(f"Could not open file: {filename}")
            result = 1

        if self.if_level < 0:
            # Found to many endifs
            self.output_print(f"Too many !ENDIF directives.")
            result = 1

        if self.if_level > 0:
            # Did find enough endifs
            self.output_print(f"Missing !ENDIF directive.")
            result = 2

        # Return the result
        return result
