import argparse
import asyncio
import logging
import re
import sys
import time
import aiohttp
import json
from secrets_file import API_KEY

server_names = {'Bailey': 20832, 'Bona': 20833, 'Campbell': 20834, 'Clark': 20835, 'Jaquez': 20836}
# Allowed communication paths
server_herd = {
    'Bailey': ['Bona', 'Clark', 'Campbell'],
    'Bona': ['Bailey', 'Clark', 'Campbell'],
    'Campbell': ['Bona', 'Bailey', 'Jaquez'],
    'Clark': ['Jaquez', 'Bona'],
    'Jaquez': ['Clark', 'Campbell']
}

class Server:
    def __init__(self, name, ip, port):
        self.name = name
        self.ip = ip
        self.port = port
        self.client_info = dict()  # client_name -> POSIX_time
        self.client_message = dict()  # client_name -> message
        logging.info("Initialize log file for server {}".format(name))
    
    async def handle_client(self, reader, writer):
        while not reader.at_eof():
            # Read data from client
            data = await reader.readline()
            message = data.decode()
            if message == "":
                continue

            # Handle incoming messages
            strings = message.split()
            
            if len(strings) == 4 and strings[0] == "IAMAT":
                await self.handle_IAMAT(strings, writer)
            elif len(strings) == 6 and strings[0] == "AT":
                await self.handle_AT(strings)
            elif len(strings) == 4 and strings[0] == "WHATSAT":
                await self.handle_WHATSAT(strings, writer)
            else:
                response_message = "? " + message
                writer.write(response_message.encode())
                await writer.drain()

        logging.info("Closing the client socket")
        writer.close()
        await writer.wait_closed()

    async def handle_IAMAT(self, strings, writer):
        client_name = strings[1]
        long_lat = strings[2]
        posix_time = strings[3]

        if self.valid_IAMAT(strings):
            # Calculate time difference
            diff = time.time() - float(posix_time)
            str_diff = f"{diff:+f}"

            # Create response message
            response_message = f"AT {self.name} {str_diff} {client_name} {long_lat} {posix_time}"

            # Update client info
            self.client_info[client_name] = float(posix_time)
            self.client_message[client_name] = response_message

            # Log and send response back to client
            logging.info(f"Sending message back to client: {response_message}")
            writer.write(response_message.encode())
            await writer.drain()

            # Call propagation function
            await self.propagate_message(response_message)
        else:
            response_message = "? " + ' '.join(strings)
            writer.write(response_message.encode())
            await writer.drain()

    async def handle_AT(self, strings):
        client_name = strings[3]
        posix_time = float(strings[5])

        if client_name not in self.client_info:
            logging.info(f"New data for client {client_name}, propagating new data...")
            self.client_info[client_name] = posix_time
            self.client_message[client_name] = ' '.join(strings)
            await self.propagate_message(' '.join(strings))
        else:
            if posix_time > self.client_info[client_name]:
                logging.info(f"Updating data for client {client_name} and propagating new data...")
                self.client_info[client_name] = posix_time
                self.client_message[client_name] = ' '.join(strings)
                await self.propagate_message(' '.join(strings))
            else:
                logging.info(f"Received outdated message for client {client_name}, not propagating.")
    
    async def handle_WHATSAT(self, strings, writer):
        client_name = strings[1]
        radius = strings[2]
        info_bound = strings[3]

        if self.valid_WHATSAT(strings):
            radius = float(radius) 
            info_bound = int(info_bound)
            if client_name not in self.client_message:
                response_message = "? " + ' '.join(strings)
                writer.write(response_message.encode())
                await writer.drain()
                return

            location = self.client_message[client_name].split()[4]
            logging.info(f"Fetching places for client {client_name} at {location} with radius {radius} and info bound {info_bound}")

            async with aiohttp.ClientSession() as session:
                places = await self.get_places(session, location, radius, info_bound)
                response_message = f"{self.client_message[client_name]}\n{places}\n\n"
                writer.write(response_message.encode())
                logging.info(f"Returned places to {client_name}")
                await writer.drain()
        else:
            response_message = "? " + ' '.join(strings)
            writer.write(response_message.encode())
            await writer.drain()

    def valid_IAMAT(self, message_parts):
        if len(message_parts) != 4:
            return False
        coord_regex = re.compile(r'^[+-]?\d+(\.\d+)?[+-]\d+(\.\d+)?$')
        if not coord_regex.match(message_parts[2]):
            return False
        try:
            float(message_parts[3])  # Check if POSIX_time is a float
            return True
        except ValueError:
            return False
    
    def valid_WHATSAT(self, message_parts):
        if len(message_parts) != 4:
            return False
        if not message_parts[2].isdigit() or not message_parts[3].isdigit():
            return False
        radius = float(message_parts[2])
        info_bound = int(message_parts[3])
        if radius > 50 or info_bound > 20:
            return False
        return True

    async def get_places(self, session, location, radius, info_bound):
        lat, long = re.match(r'([+-]?\d+\.\d+)([+-]\d+\.\d+)', location).groups()
        url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{long}&radius={radius}&key={API_KEY}"
        async with session.get(url) as response:
            data = await response.text()
            data_object = json.loads(data)
            if len(data_object["results"]) <= int(info_bound):
                return data
            else:
                data_object["results"] = data_object["results"][0:int(info_bound)]
                return json.dumps(data_object, sort_keys=True, indent=4)

    async def propagate_message(self, message):
        for server in server_herd[self.name]:
            try:
                _, writer = await asyncio.open_connection('127.0.0.1', server_names[server])
                writer.write(message.encode())
                await writer.drain()
                logging.info(f"Propagating message to {server}: {message}")
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logging.error(f"Error propagating message to {server}: {e}")
                continue

    async def run_until_interrupted(self):
        self.server = await asyncio.start_server(self.handle_client, self.ip, self.port)
        logging.info("Server {} running on {}:{}".format(self.name, self.ip, self.port))

        async with self.server:
            await self.server.serve_forever()

        logging.info("Server {} connection closed".format(self.name))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Server herd simulator")
    parser.add_argument("server_name", type=str, help="Name of the server")
    args = parser.parse_args()
    if args.server_name not in server_names:
        print("Invalid server name: {}".format(args.server_name))
        sys.exit(1)

    logging.basicConfig(filename="{}.log".format(args.server_name), level=logging.INFO, format="%(asctime)s - %(message)s")
    server = Server(args.server_name, '127.0.0.1', server_names[args.server_name])
    try:
        asyncio.run(server.run_until_interrupted())
    except KeyboardInterrupt:
        logging.info("Server shutting down")
        sys.exit(0)
    except Exception as e:
        logging.error("Server shutting down due to error: {}".format(e))
        sys.exit(1)

