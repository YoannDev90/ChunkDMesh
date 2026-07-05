using System.Diagnostics;

namespace ChunkDMesh.Client.Services;

/// <summary>Runs a quick CPU benchmark and reports chunks/second estimate.</summary>
public sealed class BenchmarkService
{
    private const int Iterations = 5;

    public BenchmarkResult Run()
    {
        var sw = Stopwatch.StartNew();
        double score = 0;

        for (int i = 0; i < Iterations; i++)
        {
            var start = Stopwatch.GetTimestamp();
            BurnCpu(TimeSpan.FromSeconds(1));
            var elapsed = Stopwatch.GetElapsedTime(start);
            score += 1.0 / elapsed.TotalSeconds;
        }

        sw.Stop();
        var avg = score / Iterations;
        var scoreNormalized = avg * 5.0; // rough mapping to chunk/second scale
        return new BenchmarkResult(scoreNormalized, sw.Elapsed.TotalSeconds, Iterations);
    }

    private static void BurnCpu(TimeSpan duration)
    {
        var start = Stopwatch.GetTimestamp();
        while (Stopwatch.GetElapsedTime(start) < duration)
        {
            // SHA-256 busy loop
            var hash = System.Security.Cryptography.SHA256.HashData(
                System.Text.Encoding.UTF8.GetBytes(Stopwatch.GetTimestamp().ToString()));
            _ = hash[0];
        }
    }
}

public sealed record BenchmarkResult(double ChunksPerSecond, double DurationSeconds, int Iterations);
