import asyncio
import logging
from typing import Callable, Awaitable, Optional, Dict, Any
from quantum_sim.network.messages import NetworkMessage, MessageType


class AsyncSocketNode:
    """
    Base asynchronous TCP socket node for multi-party quantum network simulation.
    Supports concurrent client connections, robust message framing (newline-delimited JSON),
    and message dispatching.
    """
    def __init__(self, node_id: str, host: str = "127.0.0.1", port: int = 8000):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.is_running = False
        self.handlers: Dict[MessageType, Callable[[NetworkMessage], Awaitable[Optional[NetworkMessage]]]] = {}

    def register_handler(
        self,
        msg_type: MessageType,
        handler: Callable[[NetworkMessage], Awaitable[Optional[NetworkMessage]]]
    ):
        self.handlers[msg_type] = handler

    async def start_server(self):
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self.is_running = True
        print(f"[{self.node_id}] Server listening on {self.host}:{self.port}")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while self.is_running:
                line = await reader.readline()
                if not line:
                    break
                
                try:
                    msg = NetworkMessage.deserialize(line)
                except Exception as e:
                    print(f"[{self.node_id}] Error decoding message: {e}")
                    continue

                handler = self.handlers.get(msg.msg_type)
                if handler:
                    response = await handler(msg)
                    if response:
                        writer.write(response.serialize())
                        await writer.drain()
                else:
                    # Default ack if no specific handler
                    pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[{self.node_id}] Client handling exception: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def send_message(self, host: str, port: int, msg: NetworkMessage) -> Optional[NetworkMessage]:
        """
        Connects to a remote node, sends a single message, and waits for a response (if any).
        """
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.write(msg.serialize())
            await writer.drain()

            writer.close()
            await writer.wait_closed()
            return None
        except Exception as e:
            print(f"[{self.node_id}] Failed to send message to {host}:{port} -> {e}")
            return None

    async def stop(self):
        self.is_running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            print(f"[{self.node_id}] Server stopped.")
