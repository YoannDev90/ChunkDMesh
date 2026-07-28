namespace ChunkDMesh.Client.Models;

public sealed record MetricsSnapshot
{
    public DateTime Timestamp { get; init; } = DateTime.UtcNow;
    public double ChunksPerSecond { get; init; }
    public int ActiveBatches { get; init; }
    public int TotalChunks { get; init; }
    public int BatchesCompleted { get; init; }
    public double CpuUsage { get; init; }
    public double MemoryMb { get; init; }
    public double UptimeMinutes { get; init; }
    public string CurrentRegion { get; init; } = "";
    public string Status { get; init; } = "idle";
}
