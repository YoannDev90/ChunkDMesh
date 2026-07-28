using ChunkDMesh.Client.Models;
using ChunkDMesh.Client.Services;
using ChunkDMesh.Client.Views;
using Eto.Drawing;
using Eto.Forms;

namespace ChunkDMesh.Client;

public sealed class MainForm : Form
{
    private readonly AppController _ctrl;
    private readonly MetricsService _metrics;
    private readonly NotificationService _notifications;
    private readonly DashboardView _dashboardView;
    private readonly PerformanceView _performanceView;
    private readonly LeaderboardView _leaderboardView;
    private readonly SettingsView _settingsView;
    private readonly Panel _contentArea;
    private readonly Label _statusBadge;
    private readonly ListBox _sidebar;
    private readonly UITimer _metricsTimer;
    private ThemeColors _theme = ThemeColors.Dark;
    private TrayIndicator? _tray;

    public MainForm()
    {
        Title = "ChunkDMesh Client";
        ClientSize = new Size(1100, 720);
        MinimumSize = new Size(800, 500);

        var serverUrl = "http://127.0.0.1:8000";
        _ctrl = new AppController(serverUrl);
        _metrics = new MetricsService();
        _notifications = new NotificationService();

        _ctrl.LogMessage += msg => _notifications.NotifyInfo("Log", msg);

        _dashboardView = new DashboardView(_ctrl, _metrics, _notifications);
        _performanceView = new PerformanceView(_metrics);
        _leaderboardView = new LeaderboardView(_ctrl.Api);
        _settingsView = new SettingsView(_ctrl);

        _settingsView.ThemeChanged += theme =>
        {
            _theme = theme;
            ApplyTheme(theme);
        };

        _sidebar = new ListBox
        {
            Width = 180,
            Size = new Size(180, -1),
            BackgroundColor = _theme.BgCard,
        };
        _sidebar.Items.Add("Dashboard");
        _sidebar.Items.Add("Performance");
        _sidebar.Items.Add("Leaderboard");
        _sidebar.Items.Add("Settings");
        _sidebar.SelectedIndex = 0;
        _sidebar.SelectedIndexChanged += (_, _) => SwitchView(_sidebar.SelectedIndex);

        _statusBadge = new Label
        {
            Text = "● Idle",
            TextColor = _theme.TextMuted,
            Font = Fonts.Sans(12, FontStyle.Bold),
            VerticalAlignment = VerticalAlignment.Center,
        };

        var themeToggle = new Button
        {
            Text = "☀",
            Size = new Size(32, 28),
            ToolTip = "Toggle dark/light theme",
        };
        themeToggle.Click += (_, _) =>
        {
            _theme = _theme == ThemeColors.Dark ? ThemeColors.Light : ThemeColors.Dark;
            ApplyTheme(_theme);
        };

        var header = new StackLayout
        {
            Orientation = Orientation.Horizontal,
            Padding = new Padding(12, 6),
            Spacing = 12,
            BackgroundColor = _theme.BgCard,
            Items =
            {
                new Label { Text = "ChunkDMesh", Font = Fonts.Sans(14, FontStyle.Bold), TextColor = _theme.Accent, VerticalAlignment = VerticalAlignment.Center },
                _statusBadge,
                null,
                themeToggle,
            }
        };

        _contentArea = new Panel();

        var splitter = new Splitter
        {
            Orientation = Orientation.Horizontal,
            Panel1 = _sidebar,
            Panel2 = _contentArea,
            FixedPanel = SplitterFixedPanel.Panel1,
            RelativePosition = 180,
        };

        Content = new TableLayout
        {
            Spacing = Size.Empty,
            Padding = Padding.Empty,
            Rows =
            {
                new TableRow(header),
                new TableRow(splitter) { ScaleHeight = true },
            }
        };

        try
        {
            _tray = new TrayIndicator
            {
                Title = "ChunkDMesh",
                Menu = new ContextMenu
                {
                    Items =
                    {
                        new ButtonMenuItem { Text = "Show" },
                        new ButtonMenuItem { Text = "Hide" },
                        new SeparatorMenuItem(),
                        new ButtonMenuItem { Text = "Quit" },
                    }
                },
            };
            _tray.Menu.Items[0].Click += (_, _) => Show();
            _tray.Menu.Items[1].Click += (_, _) => Visible = false;
            _tray.Menu.Items[3].Click += (_, _) => Application.Instance.Quit();
            _notifications.AttachTray(_tray);
        }
        catch { }

        _metricsTimer = new UITimer { Interval = 1 };
        _metricsTimer.Elapsed += (_, _) =>
        {
            var tl = _ctrl.TaskLoop;
            var elapsed = Math.Max((DateTime.UtcNow - _metrics.StartTime).TotalSeconds, 1);
            _metrics.RecordSample(
                tl.TotalChunks / elapsed,
                0, tl.TotalChunks, tl.BatchesCompleted, 0, 0,
                tl.CurrentRegion, tl.Status);
            RefreshHeader();
        };
        _metricsTimer.Start();

        SwitchView(0);
        _ = _ctrl.TryRestoreSessionAsync();
    }

    private void SwitchView(int index)
    {
        Control view = index switch
        {
            0 => _dashboardView,
            1 => _performanceView,
            2 => _leaderboardView,
            3 => _settingsView,
            _ => _dashboardView,
        };
        _contentArea.Content = view;
    }

    private void RefreshHeader()
    {
        var tl = _ctrl.TaskLoop;
        _statusBadge.Text = $"● {tl.Status}";
        _statusBadge.TextColor = tl.Status switch
        {
            "generating" => _theme.Warning,
            "uploading" => _theme.Accent,
            "done" => _theme.Success,
            _ => _theme.TextMuted,
        };
    }

    private void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _statusBadge.TextColor = theme.TextMuted;
        _sidebar.BackgroundColor = theme.BgCard;
        _dashboardView.ApplyTheme(theme);
        _performanceView.ApplyTheme(theme);
        _leaderboardView.ApplyTheme(theme);
        _settingsView.ApplyTheme(theme);
    }

    protected override void OnClosed(EventArgs e)
    {
        _metricsTimer.Stop();
        _tray?.Dispose();
        _ctrl.Dispose();
        base.OnClosed(e);
    }
}
