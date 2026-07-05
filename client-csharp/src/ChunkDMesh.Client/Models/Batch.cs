using System.Text.Json.Serialization;

namespace ChunkDMesh.Client.Models;

public sealed record BatchResponse
{
    [JsonPropertyName("batch_id")] public int BatchId { get; init; }
    [JsonPropertyName("regions")] public List<Region> Regions { get; init; } = [];
}

public sealed record Region
{
    [JsonPropertyName("region_x")] public int RegionX { get; init; }
    [JsonPropertyName("region_z")] public int RegionZ { get; init; }
}

public sealed record UploadResponse
{
    [JsonPropertyName("status")] public string Status { get; init; } = "";
    [JsonPropertyName("batch_id")] public int BatchId { get; init; }
    [JsonPropertyName("filename")] public string Filename { get; init; } = "";
    [JsonPropertyName("hash")] public string Hash { get; init; } = "";
}

public sealed record SubmitResponse
{
    [JsonPropertyName("status")] public string Status { get; init; } = "";
    [JsonPropertyName("batch_id")] public int BatchId { get; init; }
    [JsonPropertyName("results")] public Dictionary<string, HashResult>? Results { get; init; }
}

public sealed record HashResult
{
    [JsonPropertyName("status")] public string Status { get; init; } = "";
    [JsonPropertyName("hash")] public string? Hash { get; init; }
    [JsonPropertyName("declared_hash")] public string? DeclaredHash { get; init; }
    [JsonPropertyName("actual_hash")] public string? ActualHash { get; init; }
}

public sealed record LoginResponse
{
    [JsonPropertyName("token")] public string Token { get; init; } = "";
}

public sealed record BenchmarkRequest
{
    [JsonPropertyName("chunks_per_second")] public double ChunksPerSecond { get; init; }
    [JsonPropertyName("duration_seconds")] public double DurationSeconds { get; init; }
    [JsonPropertyName("chunks_generated")] public int ChunksGenerated { get; init; }
}

public sealed record AuthResponse
{
    [JsonPropertyName("token")] public string Token { get; init; } = "";
}

public sealed record LeaderboardEntry
{
    [JsonPropertyName("rank")] public int Rank { get; init; }
    [JsonPropertyName("mc_username")] public string McUsername { get; init; } = "";
    [JsonPropertyName("points")] public int Points { get; init; }
    [JsonPropertyName("regions")] public int Regions { get; init; }
    [JsonPropertyName("tier")] public int Tier { get; init; }
}

public sealed record LeaderboardResponse
{
    [JsonPropertyName("leaderboard")] public List<LeaderboardEntry> Leaderboard { get; init; } = [];
    [JsonPropertyName("total_contributors")] public int TotalContributors { get; init; }
    [JsonPropertyName("total_chunks_generated")] public long TotalChunksGenerated { get; init; }
}
