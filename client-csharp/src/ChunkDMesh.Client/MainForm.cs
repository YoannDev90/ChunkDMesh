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
    private readonly List<SidebarNavItem> _sidebarItems;
    private readonly StackLayout _headerBar;
    private readonly UITimer _metricsTimer;
    private readonly Panel _toastOverlay;
    private readonly Label _toastLabel;
    private ThemeColors _theme = ThemeColors.Dark;
    private TrayIndicator? _tray;
    private Button _themeToggle = default!;
    private int _selectedIndex = 0;

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
            Spacing = 0,
            BackgroundColor = _theme.BgCard,
        };

        _sidebarItems = new List<SidebarNavItem>
        {
            new SidebarNavItem(DrawDashboardIcon) { Label = "Dashboard" },
            new SidebarNavItem(DrawPerformanceIcon) { Label = "Performance" },
            new SidebarNavItem(DrawLeaderboardIcon) { Label = "Leaderboard" },
            new SidebarNavItem(DrawSettingsIcon) { Label = "Settings" },
        };

        for (int i = 0; i < _sidebarItems.Count; i++)
        {
            var idx = i;
            var item = _sidebarItems[i];
            item.IsActive = i == 0;
            item.Click += (_, _) => SelectSidebar(idx);
            item.ApplyTheme(_theme);
            _sidebarLayout.Items.Add(new StackLayoutItem(item, false));
        }

        _pageTitle = new Label
        {
            Text = "Dashboard",
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
            RelativePosition = 185,
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
            TextColor = Color.FromArgb(255, 255, 255),
            Font = Fonts.Sans(10),
            Size = new Size(400, 32),
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

    private void SelectSidebar(int index)
    {
        _selectedIndex = index;
        for (int i = 0; i < _sidebarItems.Count; i++)
        {
            _sidebarItems[i].IsActive = i == index;
            _sidebarItems[i].ApplyTheme(_theme);
        }
        SwitchView(index);
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

        _pageTitle.Text = index switch
        {
            0 => "Dashboard",
            1 => "Performance",
            2 => "Leaderboard",
            3 => "Settings",
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
        for (int i = 0; i < _sidebarItems.Count; i++)
        {
            _sidebarItems[i].IsActive = i == _selectedIndex;
            _sidebarItems[i].ApplyTheme(theme);
        }
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

    #region Sidebar Icons (drawn with Eto.Drawing primitives)

    private static void DrawDashboardIcon(Graphics g, float x, float cy, ThemeColors theme)
    {
        var s = 7f;
        var gap = 1f;
        var x0 = x;
        var x1 = x0 + s + gap;
        var x2 = x1 + s + gap;
        var x3 = x2 + s + gap;
        var yt = cy - s;
        var yc = cy;
        var yb = cy + s;
        g.FillRectangle(new SolidBrush(theme.TextSecondary), x0, yt, s, s);
        g.FillRectangle(new SolidBrush(theme.TextSecondary), x1, yt, s, s);
        g.FillRectangle(new SolidBrush(theme.TextMuted), x2, yt, s, s);
        g.FillRectangle(new SolidBrush(theme.TextMuted), x3, yt, s, s);
        g.FillRectangle(new SolidBrush(theme.Accent), x0, yc, s, s);
        g.FillRectangle(new SolidBrush(theme.Accent), x1, yc, s, s);
        g.FillRectangle(new SolidBrush(theme.TextSecondary), x2, yc, s, s);
        g.FillRectangle(new SolidBrush(theme.TextSecondary), x3, yc, s, s);
    }

    private static void DrawPerformanceIcon(Graphics g, float x, float cy, ThemeColors theme)
    {
        var pts = new[]
        {
            new PointF(x + 1, cy + 7),
            new PointF(x + 4, cy - 3),
            new PointF(x + 7, cy + 1),
            new PointF(x + 10, cy - 7),
            new PointF(x + 13, cy - 1),
            new PointF(x + 16, cy + 7),
        };
        using var pen = new Pen(theme.Accent, 2f);
        g.DrawLines(pen, pts);
    }

    private static void DrawLeaderboardIcon(Graphics g, float x, float cy, ThemeColors theme)
    {
        var cx = x + 10;
        g.DrawLine(new Pen(theme.Warning, 1.5f), cx, cy - 8, cx - 5, cy);
        g.DrawLine(new Pen(theme.Warning, 1.5f), cx, cy - 8, cx + 5, cy);
        g.DrawLine(new Pen(theme.Warning, 1.5f), cx - 5, cy, cx + 5, cy);
        g.DrawLine(new Pen(theme.Warning, 1.5f), cx - 5, cy, cx, cy + 7);
        g.DrawLine(new Pen(theme.Warning, 1.5f), cx + 5, cy, cx, cy + 7);
    }

    private static void DrawSettingsIcon(Graphics g, float x, float cy, ThemeColors theme)
    {
        var cx = x + 10;
        var r = 7f;
        g.DrawEllipse(new Pen(theme.TextSecondary, 2f), cx - r, cy - r, r * 2, r * 2);
        g.DrawEllipse(new Pen(theme.Accent, 1.5f), cx - r / 2f, cy - r / 2f, r, r);
        g.FillEllipse(new SolidBrush(theme.Accent), cx - 2, cy - 2, 4, 4);
    }

    #endregion
}

public sealed class SidebarNavItem : Drawable
{
    private readonly Action<Graphics, float, float, ThemeColors> _drawIcon;
    private ThemeColors _theme = ThemeColors.Dark;
    private bool _isActive;

    public SidebarNavItem(Action<Graphics, float, float, ThemeColors> drawIcon)
    {
        _drawIcon = drawIcon;
        Size = new Size(185, 40);
        MinimumSize = new Size(185, 40);
        BackgroundColor = ThemeColors.Dark.BgCard;
        MouseEnter += (_, _) => { if (!_isActive) { BackgroundColor = _theme.BgInput; Invalidate(); } };
        MouseLeave += (_, _) => { if (!_isActive) { BackgroundColor = _theme.BgCard; Invalidate(); } };
        MouseDown += (_, _) => Click?.Invoke(this, EventArgs.Empty);
    }

    public string Label { get; init; } = "";

    public bool IsActive
    {
        get => _isActive;
        set { _isActive = value; Invalidate(); }
    }

    public event EventHandler? Click;

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        var rect = new RectangleF(PointF.Empty, Size);
        g.FillRectangle(new SolidBrush(_isActive ? _theme.Accent : _theme.BgCard), rect);

        _drawIcon(g, 8, rect.Height / 2f, _theme);

        var labelFont = Fonts.Sans(11);
        var labelColor = _isActive ? Color.FromArgb(255, 255, 255) : _theme.TextSecondary;
        g.DrawText(labelFont, labelColor, 36, (rect.Height - 12) / 2f, Label);
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        Invalidate();
    }
}