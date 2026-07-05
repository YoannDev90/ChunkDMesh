using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using ChunkDMesh.Client.Models;

namespace ChunkDMesh.Client.Services;

public sealed class ApiService : IDisposable
{
    private readonly HttpClient _http;
    private string? _token;

    public ApiService(string serverUrl)
    {
        _http = new HttpClient
        {
            BaseAddress = new Uri(serverUrl.TrimEnd('/') + "/"),
            Timeout = TimeSpan.FromSeconds(120)
        };
    }

    public void SetToken(string token)
    {
        _token = token;
        _http.DefaultRequestHeaders.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", token);
    }

    public void ClearToken() => _http.DefaultRequestHeaders.Authorization = null;

    // ── Auth ──────────────────────────────────────────────

    public async Task<LoginResponse> LoginAsync(double powerScore, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/auth/login",
            new { power_score = powerScore }, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<LoginResponse>(cancellationToken: ct))!;
    }

    public async Task<AuthResponse> RegisterAsync(string inviteCode, double powerScore, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/auth/register",
            new { invite_code = inviteCode, power_score = powerScore }, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<AuthResponse>(cancellationToken: ct))!;
    }

    // ── Heartbeat ─────────────────────────────────────────

    public async Task HeartbeatAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/heartbeat", null, ct);
        resp.EnsureSuccessStatusCode();
    }

    // ── Benchmark ─────────────────────────────────────────

    public async Task SubmitBenchmarkAsync(double chunksPerSecond, double duration, int chunks, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/benchmark",
            new BenchmarkRequest
            {
                ChunksPerSecond = chunksPerSecond,
                DurationSeconds = duration,
                ChunksGenerated = chunks
            }, ct);
        resp.EnsureSuccessStatusCode();
    }

    // ── Tasks ─────────────────────────────────────────────

    public async Task<BatchResponse?> FetchBatchAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync("/tasks/batch", ct);
        if (resp.StatusCode == System.Net.HttpStatusCode.NotFound) return null;
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<BatchResponse>(cancellationToken: ct);
    }

    public async Task<UploadResponse> UploadMcaAsync(int batchId, string filename, byte[] zstdData, CancellationToken ct = default)
    {
        using var content = new ByteArrayContent(zstdData);
        content.Headers.Add("X-Filename", filename);
        content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream");

        var resp = await _http.PutAsync($"/tasks/upload/{batchId}", content, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<UploadResponse>(cancellationToken: ct))!;
    }

    public async Task<SubmitResponse> SubmitHashesAsync(int batchId, Dictionary<string, string> hashes, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/tasks/submit",
            new { batch_id = batchId, chunk_hashes = hashes }, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<SubmitResponse>(cancellationToken: ct))!;
    }

    // ── Assets ────────────────────────────────────────────

    public async Task<byte[]> DownloadModsZipAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync("/assets/mods.zip", ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadAsByteArrayAsync(ct);
    }

    public async Task<ServerConfig?> GetConfigAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync("/assets/config.json", ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<ServerConfig>(cancellationToken: ct);
    }

    // ── Leaderboard ─────────────────────────────────────

    public async Task<LeaderboardResponse?> GetLeaderboardAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync("/admin/leaderboard", ct);
        if (!resp.IsSuccessStatusCode) return null;
        return await resp.Content.ReadFromJsonAsync<LeaderboardResponse>(cancellationToken: ct);
    }

    // ── Tile upload ───────────────────────────────────────

    public async Task UploadTileAsync(int chunkX, int chunkZ, byte[] zstdPng, CancellationToken ct = default)
    {
        using var content = new ByteArrayContent(zstdPng);
        content.Headers.Add("X-Chunk-X", chunkX.ToString());
        content.Headers.Add("X-Chunk-Z", chunkZ.ToString());
        content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream");

        var resp = await _http.PutAsync("/tiles/upload", content, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task UploadTileBatchAsync(byte[] zstdBatch, CancellationToken ct = default)
    {
        using var content = new ByteArrayContent(zstdBatch);
        content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream");

        var resp = await _http.PutAsync("/tiles/upload/batch", content, ct);
        resp.EnsureSuccessStatusCode();
    }

    public void Dispose() => _http.Dispose();
}
