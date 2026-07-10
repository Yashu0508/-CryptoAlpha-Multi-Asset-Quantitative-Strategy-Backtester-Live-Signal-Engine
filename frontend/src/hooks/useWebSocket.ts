import { useEffect, useRef, type MutableRefObject } from "react";

/** Own a WebSocket lifecycle without defining subscription business behavior. */
export function useWebSocket(url: string): MutableRefObject<WebSocket | null> {
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(url);
    socketRef.current = socket;

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [url]);

  return socketRef;
}
