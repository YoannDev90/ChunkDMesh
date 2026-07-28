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
    private readonly Label _pageTitle;
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

        _pageTitle = new Label
        {
            Text = "Dashboard",
            Font = Fonts.Sans(18, FontStyle.Bold),
            TextColor = _theme.TextPrimary,
        };

        BuildLayout();

        _ctrl.LogMessage += msg => _feed.AddEntry("▸", msg, _theme.Accent);
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
        _startBtn = new Button { Text = "▶  Start Generation", Size = new Size(160, 36) };
        _stopBtn = new Button { Text = "■  Stop", Size = new Size(90, 36), Enabled = false };

        StyleButton(_startBtn, _theme.Accent);
        StyleButton(_stopBtn, _theme.Danger);

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
            var result = MessageBox.Show(this, "Stop generation?", "Confirm Stop",
                MessageBoxButtons.YesNo, MessageBoxType.Warning);
            if (result != DialogResult.Yes) return;

            await _ctrl.StopAsync();
            _startBtn.Enabled = true;
            _stopBtn.Enabled = false;
            _notifications.NotifyWarning("Stopped", "Generation loop halted");
        };

        var headerRow = new StackLayout
        {
            Orientation = Orientation.Horizontal,
            Spacing = 12,
            Items =
            {
                _pageTitle,
                null,
                _statusBadge,
                _startBtn,
                _stopBtn,
            }
        };

        var cardsRow = new TableRow(_cardChunks, _cardBatches, _cardRate, _cardUptime);

        var bottomRow = new TableRow
        {
            ScaleHeight = true,
            Cells =
            {
                new TableCell(_ring, false),
                new TableCell(new StackLayout
                {
                    Spacing = 6,
                    Items =
                    {
                        new Label { Text = "Activity Log", Font = Fonts.Sans(11, FontStyle.Bold), TextColor = _theme.TextPrimary },
                        new StackLayoutItem(_feed, true),
                    }
                }, true),
            }
        };

        var content = new TableLayout
        {
            Padding = new Padding(20, 12),
            Spacing = new Size(0, 16),
            Rows =
            {
                new TableRow(headerRow),
                new TableRow(cardsRow),
                new TableRow(bottomRow) { ScaleHeight = true },
            }
        };

        Content = new Scrollable { Content = content };
    }

    private static void StyleButton(Button btn, Color bgColor)
    {
        btn.BackgroundColor = bgColor;
        btn.TextColor = Color.FromArgb(255, 255, 255);
        btn.Font = Fonts.Sans(11);
        btn.Size = new Size(140, 32);
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _pageTitle.TextColor = theme.TextPrimary;
        _statusBadge.TextColor = theme.TextMuted;
        _feed.ApplyTheme(theme);
        _ring.ApplyTheme(theme);
        _cardChunks.ApplyTheme(theme);
        _cardBatches.ApplyTheme(theme);
        _cardRate.ApplyTheme(theme);
        _cardUptime.ApplyTheme(theme);
        StyleButton(_startBtn, theme.Accent);
        StyleButton(_stopBtn, theme.Danger);
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