using System.Text.RegularExpressions;

namespace ChunkDMesh.Client.Services;

public sealed partial class ChunkyService
{
    private readonly RconService _rcon;
    private static readonly Regex ProgressRegex = ChunkyProgressRegex();

    public ChunkyService(RconService rcon) => _rcon = rcon;

    public async Task SetCornersAsync(int x1, int z1, int x2, int z2, CancellationToken ct = default)
    {
        await _rcon.RunAsync($"chunks confirm", ct);
        await _rcon.RunAsync($"chunks corners {x1} {z1} {x2} {z2}", ct);
    }

    public async Task StartGenerationAsync(CancellationToken ct = default)
    {
        var resp = await _rcon.RunAsync("chunks start", ct);
        if (resp.Contains("confirm", StringComparison.OrdinalIgnoreCase))
        {
            await _rcon.RunAsync("chunks confirm", ct);
            resp = await _rcon.RunAsync("chunks start", ct);
        }
    }

    public async Task<string> StatusAsync(CancellationToken ct = default)
    {
        return await _rcon.RunAsync("chunks status", ct);
    }

    public async Task CancelAsync(CancellationToken ct = default)
    {
        await _rcon.RunAsync("chunks cancel", ct);
    }

    public ChunkyProgress ParseProgress(string raw)
    {
        var match = ProgressRegex.Match(raw);
        if (!match.Success)
            return new ChunkyProgress(0, 0, false, false);

        var done = int.Parse(match.Groups[1].Value);
        var total = int.Parse(match.Groups[2].Value);
        var finished = raw.Contains("Finished", StringComparison.OrdinalIgnoreCase)
                    || raw.Contains("100%", StringComparison.Ordinal);
        var notRunning = raw.Contains("not running", StringComparison.OrdinalIgnoreCase);

        return new ChunkyProgress(done, total, finished, notRunning);
    }

    [GeneratedRegex(@"(\d+)\s*/\s*(\d+)\s*chunks", RegexOptions.IgnoreCase)]
    private static partial Regex ChunkyProgressRegex();
}

public sealed record ChunkyProgress(int Done, int Total, bool Finished, bool NotRunning);
