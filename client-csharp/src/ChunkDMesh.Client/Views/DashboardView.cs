using ChunkDMesh.Client.Controls;
using ChunkDMesh.Client.Models;
using ChunkDMesh.Client.Services;
using Eto.Drawing;
using Eto.Forms;

namespace ChunkDMesh.Client.Views;

public sealed class DashboardView : Panel
{
    private readonly AppController _ctrl;
    private readonly MetricsService _metrics;
    private readonly NotificationService _notifications;
    private readonly ActivityFeed _feed;
    private readonly ProgressRing _ring;
    private readonly StatCard _cardChunks;
    private readonly StatCard _cardBatches;
    private readonly StatCard _cardRate;
    private readonly StatCard _cardUptime;
    private readonly Label _statusBadge;
    private ThemeColors _theme = ThemeColors.Dark;
    private Button _startBtn = default!;
    private Button _stopBtn = default!;

    public DashboardView(AppController ctrl, MetricsService metrics, NotificationService notifications)
    {
        _ctrl = ctrl;
        _metrics = metrics;
        _notifications = notifications;

        _ring = new ProgressRing();
        _feed = new ActivityFeed();

        _cardChunks = new StatCard { LabelText = "Chunks Generated", AccentColor = _theme.Success };
        _cardBatches = new StatCard { LabelText = "Batches Completed", AccentColor = _theme.Accent };
        _cardRate = new StatCard { LabelText = "Chunks/sec", AccentColor = _theme.Warning };
        _cardUptime = new StatCard { LabelText = "Uptime", AccentColor = _theme.TextMuted };

        _statusBadge = new Label
        {
            Text = "● Idle",
            TextColor = _theme.TextMuted,
            Font = Fonts.Sans(12, FontStyle.Bold),
        };

        BuildLayout();

        _ctrl.LogMessage += msg => _feed.AddEntry("ℹ", msg, _theme.Accent);
        _ctrl.StateChanged += () => Application.Instance.AsyncInvoke(RefreshStats);

        _metrics.SampleAdded += sample =>
        {
            Application.Instance.AsyncInvoke(() =>
            {
                _cardChunks.ValueText = sample.TotalChunks.ToString("N0");
                _cardBatches.ValueText = sample.BatchesCompleted.ToString();
                _cardRate.ValueText = $"{sample.ChunksPerSecond:F1}";
                _ring.Progress = sample.BatchesCompleted / Math.Max(sample.BatchesCompleted + 1f, 1f);
                _ring.CenterText = sample.Status;
                _statusBadge.Text = $"● {sample.Status}";
                _statusBadge.TextColor = sample.Status switch
                {
                    "generating" => _theme.Warning,
                    "uploading" => _theme.Accent,
                    "done" => _theme.Success,
                    _ => _theme.TextMuted,
                };
            });
        };
    }

    private void BuildLayout()
    {
        _startBtn = new Button { Text = "▶ Start Generation", Size = new Size(140, 34) };
        _stopBtn = new Button { Text = "■ Stop", Size = new Size(90, 34), Enabled = false };

        _startBtn.Click += async (_, _) =>
        {
            _startBtn.Enabled = false;
            _stopBtn.Enabled = true;
            _feed.Clear();
            _metrics.Reset();
            _notifications.NotifyInfo("Started", "Generation loop beginning...");
            _ = Task.Run(async () =>
            {
                try { await _ctrl.StartAsync(); }
                catch (Exception ex) { _ctrl.Log($"Error: {ex.Message}"); }
            });
        };

        _stopBtn.Click += async (_, _) =>
        {
            await _ctrl.StopAsync();
            _startBtn.Enabled = true;
            _stopBtn.Enabled = false;
            _notifications.NotifyWarning("Stopped", "Generation loop halted");
        };

        var controls = new TableLayout
        {
            Spacing = new Size(0, 16),
            Padding = new Padding(20),
            Rows =
            {
                new TableRow(_statusBadge, _startBtn, _stopBtn, null),
                new TableRow(_cardChunks, _cardBatches, _cardRate, _cardUptime),
                new TableRow
                {
                    ScaleHeight = true,
                    Cells =
                    {
                        new TableCell(_ring, false),
                        new TableCell(new StackLayout
                        {
                            Spacing = 8,
                            Items =
                            {
                                new Label { Text = "Activity", Font = Fonts.Sans(11, FontStyle.Bold), TextColor = _theme.TextSecondary },
                                new StackLayoutItem(_feed, true),
                            }
                        }, true),
                    }
                },
            }
        };

        Content = new Scrollable { Content = controls };
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _ring.ApplyTheme(theme);
        _feed.ApplyTheme(theme);
        _cardChunks.ApplyTheme(theme);
        _cardBatches.ApplyTheme(theme);
        _cardRate.ApplyTheme(theme);
        _cardUptime.ApplyTheme(theme);
        _statusBadge.TextColor = theme.TextMuted;
    }

    public void RefreshStats()
    {
        var elapsed = DateTime.UtcNow - _metrics.StartTime;
        _cardUptime.ValueText = elapsed.TotalHours >= 1
            ? $"{elapsed.Hours}h {elapsed.Minutes}m"
            : $"{elapsed.Minutes}m {elapsed.Seconds}s";

        var (min, max, avg) = _metrics.GetChunkRateStats();
        if (avg > 0)
            _cardRate.Subtext = $"avg {avg:F1} · max {max:F1}";

        if (_metrics.History.Count > 1)
        {
            var data = _metrics.History.Select(s => (float)s.ChunksPerSecond).ToArray();
            _cardRate.SetSparklineData(data);
        }
    }
}
