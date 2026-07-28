using ChunkDMesh.Client.Models;

namespace ChunkDMesh.Client.Services;

public sealed class MetricsService
{
    private readonly List<MetricsSnapshot> _history = [];
    private readonly int _maxSamples = 300; // 5 min at 1/sec
    private DateTime _startTime = DateTime.UtcNow;

    public IReadOnlyList<MetricsSnapshot> History => _history.AsReadOnly();
    public DateTime StartTime => _startTime;
    public TimeSpan Uptime => DateTime.UtcNow - _startTime;

    public event Action<MetricsSnapshot>? SampleAdded;

    public void Reset()
    {
        _history.Clear();
        _startTime = DateTime.UtcNow;
    }

    public void RecordSample(double chunksPerSecond, int activeBatches, int totalChunks,
        int batchesCompleted, double cpuUsage, double memoryMb, string region, string status)
    {
        var sample = new MetricsSnapshot
        {
            Timestamp = DateTime.UtcNow,
            ChunksPerSecond = chunksPerSecond,
            ActiveBatches = activeBatches,
            TotalChunks = totalChunks,
            BatchesCompleted = batchesCompleted,
            CpuUsage = cpuUsage,
            MemoryMb = memoryMb,
            UptimeMinutes = Uptime.TotalMinutes,
            CurrentRegion = region,
            Status = status,
        };

        lock (_history)
        {
            _history.Add(sample);
            if (_history.Count > _maxSamples)
                _history.RemoveAt(0);
        }

        SampleAdded?.Invoke(sample);
    }

    public (double min, double max, double avg) GetChunkRateStats()
    {
        lock (_history)
        {
            if (_history.Count == 0) return (0, 0, 0);
            var rates = _history.Where(s => s.ChunksPerSecond > 0).Select(s => s.ChunksPerSecond).ToList();
            if (rates.Count == 0) return (0, 0, 0);
            return (rates.Min(), rates.Max(), rates.Average());
        }
    }

    public double GetEstimatedTimeRemaining(int totalBatches)
    {
        lock (_history)
        {
            if (_history.Count < 2) return 0;
            var elapsed = (DateTime.UtcNow - _startTime).TotalSeconds;
            var rate = _history.Last().BatchesCompleted / Math.Max(elapsed, 1);
            var remaining = (totalBatches - _history.Last().BatchesCompleted) / Math.Max(rate, 0.001);
            return remaining;
        }
    }
}
