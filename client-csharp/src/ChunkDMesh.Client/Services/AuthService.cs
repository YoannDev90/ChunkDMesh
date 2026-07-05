using System.Text.Json;
using ChunkDMesh.Client.Models;

namespace ChunkDMesh.Client.Services;

public sealed class AuthService
{
    private readonly ApiService _api;
    private static readonly string ConfigPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        ".config", "chunkdmesh", "auth.json");

    public AuthService(ApiService api) => _api = api;

    /// <summary>Authenticate with an invite code. Returns token on success.</summary>
    public async Task<string> AuthenticateWithInviteAsync(string inviteCode, double powerScore, CancellationToken ct = default)
    {
        var resp = await _api.RegisterAsync(inviteCode, powerScore, ct);
        _api.SetToken(resp.Token);
        await SaveTokenAsync(resp.Token);
        return resp.Token;
    }

    /// <summary>Try restoring a saved token. Returns true if still valid.</summary>
    public async Task<bool> TryRestoreTokenAsync(CancellationToken ct = default)
    {
        if (!File.Exists(ConfigPath)) return false;
        var json = await File.ReadAllTextAsync(ConfigPath, ct);

        try
        {
            var data = JsonSerializer.Deserialize<StoredAuth>(json);
            if (data == null || string.IsNullOrEmpty(data.Token)) return false;

            _api.SetToken(data.Token);

            // Verify by heartbeat
            try
            {
                await _api.HeartbeatAsync(ct);
                return true;
            }
            catch
            {
                return false;
            }
        }
        catch
        {
            return false;
        }
    }

    public void Logout()
    {
        _api.ClearToken();
        if (File.Exists(ConfigPath))
            File.Delete(ConfigPath);
    }

    private static async Task SaveTokenAsync(string token)
    {
        var dir = Path.GetDirectoryName(ConfigPath)!;
        Directory.CreateDirectory(dir);

        var data = new StoredAuth { Token = token };
        await File.WriteAllTextAsync(ConfigPath, JsonSerializer.Serialize(data));
    }

    private sealed record StoredAuth { public string Token { get; init; } = ""; }
}
