using System.Text.Json.Serialization;

namespace ChunkDMesh.Client.Models;

public sealed record InviteCode
{
    private static readonly char[] Separators = ['-'];

    [JsonPropertyName("code")] public string Code { get; init; } = "";

    public bool TryParse(out string serverUrl, out string seedHash)
    {
        serverUrl = "";
        seedHash = "";

        var parts = Code.Split(Separators, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 3) return false;

        try
        {
            var decoded = Convert.FromBase64String(string.Concat(parts));
            var payload = System.Text.Encoding.UTF8.GetString(decoded);
            var segments = payload.Split('|');
            if (segments.Length >= 2)
            {
                serverUrl = segments[0];
                seedHash = segments[1];
                return true;
            }
        }
        catch { }

        return false;
    }
}
