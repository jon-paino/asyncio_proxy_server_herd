import asyncio
import aiohttp
import argparse
import sys
import logging
import json

server_names = {'Bailey' : 20832, 'Bona' : 20833, 'Campbell' : 20834, 'Clark' : 20835, 'Jaquez' : 20836}
# Allowed communication paths
server_herd = {
    'Bailey': ['Bona', 'Clark', 'Campbell'],
    'Bona': ['Bailey', 'Clark', 'Campbell'],
    'Campbell': ['Bona', 'Bailey', 'Jaquez'],
    'Clark': ['Jaquez', 'Bona'],
    'Jaquez': ['Clark', 'Campbell'] 
}

class Server:
    def init(self, name, host, port):
        self.name = name
        self.host = host
        self.port = port
    
    async def handle_client(self, reader, writer):
        pass

    async def run_until_interrupted(self):
        # start the server
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)

        logging.info("Server {} running on {}:{}".format(self.name, self.host, self.port))

        # keep the server running until interrupted 
        async with self.server:
            await self.server.serve_forever()

        logging.info("Server {} connection closed".format(self.name))




        








if __name__ == "__main__":
    # Create and argument parser
    parser = argparse.ArgumentParser(description="Server herd simulator")
    parser.add_argument("server_name", type=str, help="Name of the server")
    args = parser.parse_args()
    if args.server_name not in server_names:
        print("Invalid server name: {}".format(args.server_name))
        sys.exit(1)

    logging.basicConfig(filename="{}.log".format(args.server_name), level=logging.INFO, format="%(asctime)s - %(message)s")
    # Initialize the server and try and run it
    server = Server(args.server_name, '127.0.0.1', server_names[args.server_name])
    try:
        asyncio.run(server.run_until_interrupted())
    except KeyboardInterrupt:
        logging.info("Server shutting down")
        sys.exit(0)
    except Exception as e:
        logging.error("Server shutting down due to error: {}".format(e))
        sys.exit(1)


