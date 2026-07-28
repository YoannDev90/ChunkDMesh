using Eto.Drawing;
using Eto.Forms;

namespace ChunkDMesh.Client.Services;

public sealed class NotificationService
{
    private TrayIndicator? _tray;
    private Panel? _overlay;
    private Label? _toastLabel;
    private Window? _ownerWindow;

    public void AttachTray(TrayIndicator tray) => _tray = tray;

    public void AttachToastOverlay(Panel overlay, Label toastLabel, Window owner)
    {
        _overlay = overlay;
        _toastLabel = toastLabel;
        _ownerWindow = owner;
    }

    public void NotifyInfo(string title, string message)
    {
        System.Diagnostics.Debug.WriteLine($"[INFO] {title}: {message}");
        ShowToast(title, message, Color.FromArgb(52, 211, 153));
    }

    public void NotifyWarning(string title, string message)
    {
        System.Diagnostics.Debug.WriteLine($"[WARN] {title}: {message}");
        ShowToast(title, message, Color.FromArgb(251, 191, 36));
    }

    public void NotifyError(string title, string message)
    {
        System.Diagnostics.Debug.WriteLine($"[ERR] {title}: {message}");
        ShowToast(title, message, Color.FromArgb(239, 68, 68));
    }

    public void NotifyGenerationComplete(int batchId, string region, double elapsedSec)
    {
        NotifyInfo("Region Complete", $"Batch #{batchId} — region {region} done in {elapsedSec:F0}s");
    }

    public void NotifyRewardEarned(string item, int quantity, string reason)
    {
        NotifyInfo("Reward Earned!", $"You received {quantity}x {item} — {reason}");
    }

    public void NotifyBenchmarkResult(double chunksPerSec)
    {
        NotifyInfo("Benchmark Complete", $"Score: {chunksPerSec:F1} chunks/sec");
    }

    private void ShowToast(string title, string message, Color accentColor)
    {
        try
        {
            if (_overlay == null || _toastLabel == null || _ownerWindow == null) return;

            Application.Instance.AsyncInvoke(() =>
            {
                _toastLabel.Text = $"✅ {title}: {message}";
                _toastLabel.BackgroundColor = accentColor;
                _toastLabel.TextColor = Color.FromArgb(255, 255, 255);
                _toastLabel.Font = Fonts.Sans(10);
                _toastLabel.Size = new Size(400, 32);
                _toastLabel.VerticalAlignment = VerticalAlignment.Center;
                _overlay.Visible = true;

                Task.Delay(3000).ContinueWith(_ =>
                {
                    Application.Instance.AsyncInvoke(() => _overlay.Visible = false);
                }, TaskScheduler.FromCurrentSynchronizationContext());
            });
        }
        catch { }
    }
}