import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;

/** Send Kodi EventServer packets through one Android-local UDP socket. */
public final class MwoKodiEventSender {
    private MwoKodiEventSender() {}

    private static byte[] decodeHex(String value) {
        if ((value.length() & 1) != 0) {
            throw new IllegalArgumentException("hex packet has odd length");
        }
        byte[] result = new byte[value.length() / 2];
        for (int index = 0; index < value.length(); index += 2) {
            int high = Character.digit(value.charAt(index), 16);
            int low = Character.digit(value.charAt(index + 1), 16);
            if (high < 0 || low < 0) {
                throw new IllegalArgumentException("hex packet is invalid");
            }
            result[index / 2] = (byte) ((high << 4) | low);
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            throw new IllegalArgumentException(
                "usage: SOURCE_PORT DESTINATION_PORT PACKET_HEX..."
            );
        }
        int sourcePort = Integer.parseInt(args[0]);
        int destinationPort = Integer.parseInt(args[1]);
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (DatagramSocket socket = new DatagramSocket(sourcePort, loopback)) {
            for (int index = 2; index < args.length; index++) {
                byte[] payload = decodeHex(args[index]);
                socket.send(
                    new DatagramPacket(
                        payload, payload.length, loopback, destinationPort
                    )
                );
                if (index + 1 < args.length) {
                    Thread.sleep(25L);
                }
            }
        }
    }
}
