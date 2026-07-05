using System.Net.Sockets;
using System.Text;

namespace ChunkDMesh.Client.Services;

/// <summary>
/// Minecraft RCON client. Protocol: 4-byte length + 4-byte request ID + 4-byte type + payload + 2-byte padding.
/// </summary>
public sealed class RconService : IDisposable
{
    private readonly string _host;
    private readonly int _port;
    private readonly string _password;
    private TcpClient? _tcp;
    private NetworkStream? _stream;
    private int _requestId;

    public RconService(string host, int port, string password)
    {
        _host = host;
        _port = port;
        _password = password;
    }

    public async Task ConnectAsync(CancellationToken ct = default)
    {
        _tcp = new TcpClient();
        await _tcp.ConnectAsync(_host, _port, ct);
        _stream = _tcp.GetStream();

        // Auth
        var resp = await SendPacketAsync(3, _password, ct);
        if (resp.RequestId == -1)
            throw new InvalidOperationException("RCON authentication failed");
    }

    public async Task<string> RunAsync(string command, CancellationToken ct = default)
    {
        var resp = await SendPacketAsync(2, command, ct);
        return Encoding.UTF8.GetString(resp.Payload).TrimEnd('\0', '\n', '\r');
    }

    public async Task<string> RunChunkyAsync(params string[] args)
    {
        return await RunAsync("chunky " + string.Join(" ", args));
    }

    private async Task<RconPacket> SendPacketAsync(int type, string payload, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(_stream);

        var id = Interlocked.Increment(ref _requestId);
        var body = Encoding.UTF8.GetBytes(payload);
        var len = 4 + 4 + body.Length + 2; // id + type + payload + padding
        var packet = new byte[len + 4]; // +4 for length prefix

        BitConverter.GetBytes(len).CopyTo(packet, 0);
        BitConverter.GetBytes(id).CopyTo(packet, 4);
        BitConverter.GetBytes(type).CopyTo(packet, 8);
        body.CopyTo(packet, 12);

        await _stream.WriteAsync(packet, ct);
        await _stream.FlushAsync(ct);

        // Read response
        var header = new byte[12];
        var read = 0;
        while (read < 12)
            read += await _stream.ReadAsync(header.AsMemory(read, 12 - read), ct);

        var respLen = BitConverter.ToInt32(header, 0);
        var respId = BitConverter.ToInt32(header, 4);
        var respType = BitConverter.ToInt32(header, 8);

        var respBody = new byte[Math.Max(0, respLen - 8)]; // minus id + type
        read = 0;
        while (read < respBody.Length)
            read += await _stream.ReadAsync(respBody.AsMemory(read, respBody.Length - read), ct);

        return new RconPacket(respId, respType, respBody);
    }

    public void Dispose()
    {
        _stream?.Dispose();
        _tcp?.Dispose();
    }

    private sealed record RconPacket(int RequestId, int Type, byte[] Payload);
}
