using ChunkDMesh.Client.Models;
using ChunkDMesh.Client.Services;
using Eto.Drawing;
using Eto.Forms;

namespace ChunkDMesh.Client.Views;

public sealed class LeaderboardView : Panel
{
    private readonly ApiService _api;
    private readonly GridView<LeaderboardEntry> _grid;
    private readonly Label _totalLabel;
    private readonly Label _chunksLabel;
    private readonly Label _myRankLabel;
    private readonly TextBox _searchBox;
    private Label _pageTitle;
    private Label _lastRefresh;
    private ThemeColors _theme = ThemeColors.Dark;
    private readonly UITimer _refreshTimer;
    private List<LeaderboardEntry> _allEntries = [];

    public LeaderboardView(ApiService api)
    {
        _api = api;

        _totalLabel = new Label { Font = Fonts.Sans(11), TextColor = _theme.TextSecondary };
        _chunksLabel = new Label { Font = Fonts.Sans(11), TextColor = _theme.TextSecondary };
        _myRankLabel = new Label { Font = Fonts.Sans(18, FontStyle.Bold), TextColor = _theme.Accent };

        _searchBox = new TextBox
        {
            Width = 200,
            PlaceholderText = "Search players...",
            BackgroundColor = _theme.BgInput,
            TextColor = _theme.TextPrimary,
            Font = Fonts.Sans(11),
        };

        _grid = new GridView<LeaderboardEntry>
        {
            AllowColumnReordering = false,
        };

        _grid.Columns.Add(new GridColumn { HeaderText = "", Width = 40, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.Rank.ToString()) } });
        _grid.Columns.Add(new GridColumn { HeaderText = "Player", Width = 180, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.McUsername) } });
        _grid.Columns.Add(new GridColumn { HeaderText = "Points", Width = 90, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.Points.ToString()) } });
        _grid.Columns.Add(new GridColumn { HeaderText = "Regions", Width = 80, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.Regions.ToString()) } });
        _grid.Columns.Add(new GridColumn { HeaderText = "Tier", Width = 60, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.Tier.ToString()) } });

        _pageTitle = new Label
        {
            Text = "Community Leaderboard",
            Font = Fonts.Sans(18, FontStyle.Bold),
            TextColor = _theme.TextPrimary,
        };

        _lastRefresh = new Label
        {
            Text = "",
            Font = Fonts.Sans(9),
            TextColor = _theme.TextMuted,
        };

        BuildLayout();

        _searchBox.TextChanged += (_, _) => ApplyFilter();

        _refreshTimer = new UITimer { Interval = 15 };
        _refreshTimer.Elapsed += async (_, _) => await RefreshAsync();
        _refreshTimer.Start();

        _ = RefreshAsync();
    }

    private void BuildLayout()
    {
        var headerRow = new StackLayout
        {
            Orientation = Orientation.Horizontal,
            Spacing = 12,
            Items =
            {
                _pageTitle,
                null,
                _lastRefresh,
            }
        };

        var statsRow = new StackLayout
        {
            Orientation = Orientation.Horizontal,
            Spacing = 20,
            Items =
            {
                _myRankLabel,
                _totalLabel,
                _chunksLabel,
            }
        };

        var searchRow = new StackLayout
        {
            Orientation = Orientation.Horizontal,
            Spacing = 8,
            Items =
            {
                new Label { Text = "🔍", Font = Fonts.Sans(11), VerticalAlignment = VerticalAlignment.Center },
                _searchBox,
            }
        };

        var content = new TableLayout
        {
            Padding = new Padding(20, 12),
            Spacing = new Size(0, 12),
            Rows =
            {
                new TableRow(headerRow),
                new TableRow(statsRow),
                new TableRow(searchRow),
                new TableRow { ScaleHeight = true, Cells = { new TableCell(_grid, true) } },
            }
        };

        Content = new Scrollable { Content = content };
    }

    private void ApplyFilter()
    {
        var query = _searchBox.Text.Trim().ToLowerInvariant();
        if (string.IsNullOrEmpty(query))
        {
            _grid.DataStore = _allEntries;
            return;
        }

        _grid.DataStore = _allEntries.Where(e =>
            e.McUsername.ToLowerInvariant().Contains(query)).ToList();
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _pageTitle.TextColor = theme.TextPrimary;
        _myRankLabel.TextColor = theme.Accent;
        _totalLabel.TextColor = theme.TextSecondary;
        _chunksLabel.TextColor = theme.TextSecondary;
        _lastRefresh.TextColor = theme.TextMuted;
        _searchBox.BackgroundColor = theme.BgInput;
        _searchBox.TextColor = theme.TextPrimary;
    }

    public async Task RefreshAsync()
    {
        try
        {
            var lb = await _api.GetLeaderboardAsync();
            if (lb == null) return;

            _allEntries = lb.Leaderboard;
            _lastRefresh.Text = $"Updated {DateTime.Now:HH:mm:ss}";

            ApplyFilter();

            Application.Instance.AsyncInvoke(() =>
            {
                _totalLabel.Text = $"Contributors: {lb.TotalContributors}";
                _chunksLabel.Text = $"Total chunks: {lb.TotalChunksGenerated:N0}";
                _myRankLabel.Text = $"{lb.Leaderboard.Count} players";
            });
        }
        catch (Exception ex)
        {
            _lastRefresh.Text = $"Error: {ex.Message}";
        }
    }
}