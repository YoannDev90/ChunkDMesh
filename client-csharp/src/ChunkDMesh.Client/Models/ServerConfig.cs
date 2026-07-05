using System.Text.Json.Serialization;

namespace ChunkDMesh.Client.Models;

public sealed record ServerConfig
{
    [JsonPropertyName("minecraft_version")] public string MinecraftVersion { get; init; } = "";
    [JsonPropertyName("minecraft_loader")] public string MinecraftLoader { get; init; } = "";
    [JsonPropertyName("loader_version")] public string LoaderVersion { get; init; } = "";
    [JsonPropertyName("chunky_version")] public string ChunkyVersion { get; init; } = "";
    [JsonPropertyName("world_name")] public string WorldName { get; init; } = "";
    [JsonPropertyName("dimension")] public string Dimension { get; init; } = "overworld";
    [JsonPropertyName("seed")] public long Seed { get; init; }
    [JsonPropertyName("radius")] public int Radius { get; init; } = 1024;
    [JsonPropertyName("shape")] public string Shape { get; init; } = "square";
    [JsonPropertyName("pattern")] public string Pattern { get; init; } = "regions";
    [JsonPropertyName("max_clients")] public int MaxClients { get; init; } = 100;
    [JsonPropertyName("chunk_format")] public string ChunkFormat { get; init; } = "sha256";
    [JsonPropertyName("verification")] public bool Verification { get; init; }
    [JsonPropertyName("has_mods_zip")] public bool HasModsZip { get; init; }
}
