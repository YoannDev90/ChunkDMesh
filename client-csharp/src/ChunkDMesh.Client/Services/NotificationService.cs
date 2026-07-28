using Eto.Forms;

namespace ChunkDMesh.Client.Services;

public sealed class NotificationService
{
    private TrayIndicator? _tray;

    public void AttachTray(TrayIndicator tray) => _tray = tray;

    public void NotifyInfo(string title, string message)
    {
        System.Diagnostics.Debug.WriteLine($"[INFO] {title}: {message}");
    }

    public void NotifyWarning(string title, string message)
    {
        System.Diagnostics.Debug.WriteLine($"[WARN] {title}: {message}");
    }

    public void NotifyError(string title, string message)
    {
        System.Diagnostics.Debug.WriteLine($"[ERR] {title}: {message}");
    }

    public void NotifyGenerationComplete(int batchId, string region, double elapsedSec)
    {
        NotifyInfo("Region Complete",
            $"Batch #{batchId} — region {region} done in {elapsedSec:F0}s");
    }

    public void NotifyRewardEarned(string item, int quantity, string reason)
    {
        NotifyInfo("Reward Earned!",
            $"You received {quantity}x {item} — {reason}");
    }

    public void NotifyBenchmarkResult(double chunksPerSec)
    {
        NotifyInfo("Benchmark Complete",
            $"Score: {chunksPerSec:F1} chunks/sec");
    }
}
