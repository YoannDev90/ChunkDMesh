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
    private readonly Label _pageTitle;
    private readonly StackLayout _sidebarLayout;
    private readonly List<Button> _sidebarButtons;
    private readonly StackLayout _headerBar;
    private readonly UITimer _metricsTimer;
    private readonly Panel _toastOverlay;
    private readonly Label _toastLabel;
    private ThemeColors _theme = ThemeColors.Dark;
    private TrayIndicator? _tray;
    private Button _themeToggle = default!;

    public MainForm()
    {
        Title = "ChunkDMesh Client";
        ClientSize = new Size(1100, 720);
        MinimumSize = new Size(800, 500);

        var serverUrl = "http://127.0.0.1:8000";
        _ctrl = new AppController(serverUrl);
        _metrics = new MetricsService();
        _notifications = new NotificationService();

        _dashboardView = new DashboardView(_ctrl, _metrics, _notifications);
        _performanceView = new PerformanceView(_metrics);
        _leaderboardView = new LeaderboardView(_ctrl.Api);
        _settingsView = new SettingsView(_ctrl);

        _settingsView.ThemeChanged += theme =>
        {
            _theme = theme;
            ApplyTheme(theme);
        };

        _sidebarLayout = new StackLayout
        {
            Orientation = Orientation.Vertical,
            Padding = new Padding(0),
            Spacing = 2,
            BackgroundColor = _theme.BgCard,
        };

        _sidebarButtons = new List<Button>();
        var sidebarItems = new[]
        {
            (Icon: "▣", Label: " Dashboard"),
            (Icon: "▤", Label: " Performance"),
            (Icon: "▥", Label: " Leaderboard"),
            (Icon: "⚙", Label: " Settings"),
        };

        for (int i = 0; i < sidebarItems.Length; i++)
        {
            var item = sidebarItems[i];
            var btn = new Button
            {
                Text = $"  {item.Icon}{item.Label}",
                Font = Fonts.Sans(12),
                BackgroundColor = i == 0 ? _theme.Accent : _theme.BgCard,
                TextColor = i == 0 ? Color.FromArgb(255, 255, 255) : _theme.TextSecondary,
                Size = new Size(185, 44),
                MinimumSize = new Size(185, 44),
            };
            btn.Click += (_, _) => SelectSidebar(i);
            _sidebarButtons.Add(btn);
            _sidebarLayout.Items.Add(new StackLayoutItem(btn, false));
        }

        _pageTitle = new Label
        {
            Text = "📊 Dashboard",
            Font = Fonts.Sans(16, FontStyle.Bold),
            TextColor = _theme.TextPrimary,
        };

        _statusBadge = new Label
        {
            Text = "● Idle",
            TextColor = _theme.TextMuted,
            Font = Fonts.Sans(12, FontStyle.Bold),
            VerticalAlignment = VerticalAlignment.Center,
        };

        _themeToggle = new Button
        {
            Text = "☀",
            Size = new Size(32, 28),
            ToolTip = "Toggle dark/light theme",
        };
        _themeToggle.Click += (_, _) =>
        {
            _theme = _theme == ThemeColors.Dark ? ThemeColors.Light : ThemeColors.Dark;
            ApplyTheme(_theme);
        };

        _headerBar = new StackLayout
        {
            Orientation = Orientation.Horizontal,
            Padding = new Padding(12, 6),
            Spacing = 12,
            BackgroundColor = _theme.BgCard,
            Items =
            {
                _pageTitle,
                null,
                _statusBadge,
                _themeToggle,
            }
        };

        _contentArea = new Panel();

        var splitter = new Splitter
        {
            Orientation = Orientation.Horizontal,
            Panel1 = _sidebarLayout,
            Panel2 = _contentArea,
            FixedPanel = SplitterFixedPanel.Panel1,
            RelativePosition = 180,
        };

        _toastOverlay = new Panel
        {
            Visible = false,
            BackgroundColor = Color.FromArgb(200, 0, 0, 0),
            Size = new Size(400, 32),
        };

        _toastLabel = new Label
        {
            Text = "",
            TextColor = Colors.White,
            Font = Fonts.Sans(10),
        };
        _toastOverlay.Content = _toastLabel;

        Content = new TableLayout
        {
            Spacing = Size.Empty,
            Padding = Padding.Empty,
            Rows =
            {
                new TableRow(_headerBar),
                new TableRow(splitter) { ScaleHeight = true },
                new TableRow(_toastOverlay),
            }
        };

        _notifications.AttachToastOverlay(_toastOverlay, _toastLabel, this);

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

        SelectSidebar(0);
        _ = _ctrl.TryRestoreSessionAsync();
    }

    private void SwitchView(int index)
    {
        SelectedSidebarIndex = index;
        Control view = index switch
        {
            0 => _dashboardView,
            1 => _performanceView,
            2 => _leaderboardView,
            3 => _settingsView,
            _ => _dashboardView,
        };
        _contentArea.Content = view;

        _pageTitle.Text = index switch
        {
            0 => "📊 Dashboard",
            1 => "⚡ Performance",
            2 => "🏆 Leaderboard",
            3 => "⚙️ Settings",
            _ => "ChunkDMesh",
        };
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

    private void SelectSidebar(int index)
    {
        for (int i = 0; i < _sidebarButtons.Count; i++)
        {
            var btn = _sidebarButtons[i];
            btn.BackgroundColor = i == index ? _theme.Accent : _theme.BgCard;
            btn.TextColor = i == index ? Color.FromArgb(255, 255, 255) : _theme.TextSecondary;
        }
        SwitchView(index);
    }

    private void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _headerBar.BackgroundColor = theme.BgCard;
        _pageTitle.TextColor = theme.TextPrimary;
        _statusBadge.TextColor = theme.TextMuted;
        _themeToggle.BackgroundColor = theme.BgCard;
        _toastOverlay.BackgroundColor = Color.FromArgb(200, 0, 0, 0);
        _sidebarLayout.BackgroundColor = theme.BgCard;
        _sidebarButtons[SelectedSidebarIndex].BackgroundColor = theme.Accent;
        for (int i = 0; i < _sidebarButtons.Count; i++)
        {
            _sidebarButtons[i].TextColor = i == SelectedSidebarIndex ? Color.FromArgb(255, 255, 255) : theme.TextSecondary;
        }
        _dashboardView.ApplyTheme(theme);
        _performanceView.ApplyTheme(theme);
        _leaderboardView.ApplyTheme(theme);
        _settingsView.ApplyTheme(theme);
    }

    private int SelectedSidebarIndex = 0;

    protected override void OnClosed(EventArgs e)
    {
        _metricsTimer.Stop();
        _tray?.Dispose();
        _ctrl.Dispose();
        base.OnClosed(e);
    }
}