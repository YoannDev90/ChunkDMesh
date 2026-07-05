using System.Diagnostics;
using System.Security.Cryptography;
using ChunkDMesh.Client.Models;
using ZstdSharp;

namespace ChunkDMesh.Client.Services;

public sealed class TaskLoopService
{
    private readonly ApiService _api;
    private readonly MinecraftService _mc;
    private readonly RconService _rcon;
    private readonly ChunkyService _chunky;
    private readonly string _regionDir;

    public TaskLoopService(ApiService api, MinecraftService mc, RconService rcon, ChunkyService chunky)
    {
        _api = api;
        _mc = mc;
        _rcon = rcon;
        _chunky = chunky;
        _regionDir = Path.Combine(mc.ServerDir, "world", "region");
    }

    public int BatchesCompleted { get; private set; }
    public int TotalChunks { get; private set; }
    public string CurrentRegion { get; private set; } = "";
    public string Status { get; private set; } = "idle";

    public event Action? StateChanged;

    public async Task RunLoopAsync(CancellationToken ct = default)
    {
        while (!ct.IsCancellationRequested)
        {
            Status = "fetching";
            StateChanged?.Invoke();

            BatchResponse? batch;
            try
            {
                batch = await _api.FetchBatchAsync(ct);
            }
            catch (HttpRequestException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
            {
                Status = "done — no more tasks";
                StateChanged?.Invoke();
                return;
            }

            if (batch == null || batch.Regions.Count == 0)
            {
                Status = "done";
                StateChanged?.Invoke();
                return;
            }

            var region = batch.Regions[0];
            var rx = region.RegionX;
            var rz = region.RegionZ;
            CurrentRegion = $"({rx}, {rz})";
            var x1 = rx * 512;
            var z1 = rz * 512;
            var x2 = rx * 512 + 511;
            var z2 = rz * 512 + 511;

            Status = $"generating region {CurrentRegion}";
            StateChanged?.Invoke();

            await GenerateRegionAsync(x1, z1, x2, z2, ct);

            Status = $"uploading region {CurrentRegion}";
            StateChanged?.Invoke();
            await UploadAndSubmitAsync(batch.BatchId, region, ct);

            BatchesCompleted++;
            StateChanged?.Invoke();
        }
    }

    private async Task GenerateRegionAsync(int x1, int z1, int x2, int z2, CancellationToken ct)
    {
        await _rcon.RunAsync("save-all", ct);
        await Task.Delay(3000, ct);

        await _rcon.RunAsync("chunky world world", ct);
        await _chunky.SetCornersAsync(x1, z1, x2, z2, ct);
        await _rcon.RunAsync("chunky shape square", ct);
        await _rcon.RunAsync("chunky pattern loop", ct);

        await _chunky.StartGenerationAsync(ct);

        var start = Stopwatch.GetTimestamp();
        const double timeout = 1800.0;

        while (!ct.IsCancellationRequested)
        {
            var elapsed = Stopwatch.GetElapsedTime(start).TotalSeconds;
            if (elapsed > timeout)
            {
                await _chunky.CancelAsync(ct);
                return;
            }

            var raw = await _chunky.StatusAsync(ct);
            var progress = _chunky.ParseProgress(raw);

            if (progress.Finished || progress.Done >= 1024)
                break;

            if (progress.NotRunning && elapsed > 30)
                break;

            await Task.Delay(2000, ct);
        }

        TotalChunks += 1024;
    }

    private async Task UploadAndSubmitAsync(int batchId, Region region, CancellationToken ct)
    {
        var expectedFile = Path.Combine(_regionDir, $"r.{region.RegionX}.{region.RegionZ}.mca");

        for (int i = 0; i < 60; i++)
        {
            if (File.Exists(expectedFile))
            {
                var size1 = new FileInfo(expectedFile).Length;
                await Task.Delay(500, ct);
                var size2 = new FileInfo(expectedFile).Length;
                if (size1 == size2 && size1 > 0)
                    break;
            }
            await Task.Delay(1000, ct);
        }

        if (!File.Exists(expectedFile))
            return;

        await _rcon.RunAsync("save-all", ct);
        await Task.Delay(2000, ct);

        // Hash
        await using var fs = File.OpenRead(expectedFile);
        var sha256 = await SHA256.HashDataAsync(fs, ct);
        var hash = Convert.ToHexString(sha256).ToLowerInvariant();
        fs.Position = 0;

        // Zstd compress
        var rawData = await File.ReadAllBytesAsync(expectedFile, ct);
        var zstdData = ZstdSharp.Zstd.Compress(rawData, 19);

        var filename = Path.GetFileName(expectedFile);
        await _api.UploadMcaAsync(batchId, filename, zstdData, ct);

        var hashes = new Dictionary<string, string> { [filename] = hash };
        await _api.SubmitHashesAsync(batchId, hashes, ct);
    }
}
