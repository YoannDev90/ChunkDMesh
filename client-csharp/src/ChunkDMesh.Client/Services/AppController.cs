using ChunkDMesh.Client.Models;

namespace ChunkDMesh.Client.Services;

/// <summary>Orchestrates all services. Single point of control for the UI.</summary>
public sealed class AppController : IDisposable
{
    private readonly ApiService _api;
    private readonly AuthService _auth;
    private readonly MinecraftService _mc;
    private readonly RconService _rcon;
    private readonly ChunkyService _chunky;
    private readonly TaskLoopService _taskLoop;
    private CancellationTokenSource? _cts;

    public AppController(string serverUrl)
    {
        _api = new ApiService(serverUrl);
        _auth = new AuthService(_api);
        _mc = new MinecraftService(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".chunkdmesh"));
        _rcon = new RconService("127.0.0.1", 25575, "");
        _chunky = new ChunkyService(_rcon);
        _taskLoop = new TaskLoopService(_api, _mc, _rcon, _chunky);
    }

    public ApiService Api => _api;
    public AuthService Auth => _auth;
    public MinecraftService Mc => _mc;
    public RconService Rcon => _rcon;
    public ChunkyService Chunky => _chunky;
    public TaskLoopService TaskLoop => _taskLoop;

    public bool IsRunning => _cts != null;

    public event Action<string>? LogMessage;
    public event Action? StateChanged;

    public void Log(string msg) => LogMessage?.Invoke(msg);

    public async Task<bool> TryRestoreSessionAsync(CancellationToken ct = default)
    {
        return await _auth.TryRestoreTokenAsync(ct);
    }

    public async Task<string> LoginWithInviteAsync(string inviteCode, CancellationToken ct = default)
    {
        var bench = new BenchmarkService();
        var result = bench.Run();
        LogMessage?.Invoke($"Benchmark: {result.ChunksPerSecond:F1} chunks/s");

        var token = await _auth.AuthenticateWithInviteAsync(inviteCode, result.ChunksPerSecond, ct);

        // Submit benchmark
        await _api.SubmitBenchmarkAsync(result.ChunksPerSecond, result.DurationSeconds, result.Iterations, ct);

        LogMessage?.Invoke("Authenticated successfully");
        return token;
    }

    public async Task StartAsync(CancellationToken ct = default)
    {
        _cts = CancellationTokenSource.CreateLinkedTokenSource(ct);

        LogMessage?.Invoke("Setting up Minecraft environment...");

        // Java
        if (_mc.DetectJava() == null)
        {
            LogMessage?.Invoke("Java not found, downloading...");
            await _mc.DownloadJavaAsync(new Progress<double>(p => LogMessage?.Invoke($"Java: {p:P0}")));
        }
        LogMessage?.Invoke($"Java: {_mc.JavaPath}");

        // Config
        var config = await _api.GetConfigAsync(_cts.Token);
        if (config == null) throw new InvalidOperationException("Failed to get server config");
        LogMessage?.Invoke($"World: {config.WorldName} ({config.Dimension})");

        // Mods
        if (config.HasModsZip)
        {
            LogMessage?.Invoke("Downloading mods...");
            var mods = await _api.DownloadModsZipAsync(_cts.Token);
            await _mc.DownloadModsAsync(mods, _cts.Token);
        }

        // Server properties
        await _mc.WriteServerPropertiesAsync(25575, "", _cts.Token);

        // Launch MC
        LogMessage?.Invoke("Starting Minecraft server...");
        await _mc.LaunchServerAsync(_cts.Token);

        // Connect RCON
        await _rcon.ConnectAsync(_cts.Token);
        LogMessage?.Invoke("RCON connected");

        // Run loop
        _taskLoop.StateChanged += () => StateChanged?.Invoke();
        LogMessage?.Invoke("Starting generation loop...");
        await _taskLoop.RunLoopAsync(_cts.Token);

        LogMessage?.Invoke($"Done! {_taskLoop.BatchesCompleted} batches generated.");
    }

    public async Task StopAsync()
    {
        _cts?.Cancel();
        await _mc.StopServerAsync();
    }

    public void Dispose()
    {
        _cts?.Dispose();
        _api.Dispose();
        _rcon.Dispose();
    }
}
