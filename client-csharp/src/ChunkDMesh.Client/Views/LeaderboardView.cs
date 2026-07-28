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
    private ThemeColors _theme = ThemeColors.Dark;
    private readonly UITimer _refreshTimer;

    public LeaderboardView(ApiService api)
    {
        _api = api;

        _totalLabel = new Label { Font = Fonts.Sans(11), TextColor = _theme.TextSecondary };
        _chunksLabel = new Label { Font = Fonts.Sans(11), TextColor = _theme.TextSecondary };
        _myRankLabel = new Label { Font = Fonts.Sans(18, FontStyle.Bold), TextColor = _theme.Accent };

        _grid = new GridView<LeaderboardEntry>
        {
            Size = new Size(600, 300),
            AllowColumnReordering = false,
        };

        _grid.Columns.Add(new GridColumn { HeaderText = "#", Width = 40, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.Rank.ToString()) } });
        _grid.Columns.Add(new GridColumn { HeaderText = "Player", Width = 160, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.McUsername) } });
        _grid.Columns.Add(new GridColumn { HeaderText = "Points", Width = 80, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.Points.ToString()) } });
        _grid.Columns.Add(new GridColumn { HeaderText = "Regions", Width = 80, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.Regions.ToString()) } });
        _grid.Columns.Add(new GridColumn { HeaderText = "Tier", Width = 60, DataCell = new TextBoxCell { Binding = Binding.Property((LeaderboardEntry e) => e.Tier.ToString()) } });

        BuildLayout();

        _refreshTimer = new UITimer { Interval = 15 };
        _refreshTimer.Elapsed += async (_, _) => await RefreshAsync();
        _refreshTimer.Start();

        _ = RefreshAsync();
    }

    private void BuildLayout()
    {
        Content = new Scrollable
        {
            Content = new TableLayout
            {
                Padding = new Padding(20),
                Spacing = new Size(0, 12),
                Rows =
                {
                    new TableRow(new Label { Text = "Community Leaderboard", Font = Fonts.Sans(14, FontStyle.Bold), TextColor = _theme.TextPrimary }),
                    new TableRow(_myRankLabel, _totalLabel, _chunksLabel),
                    new TableRow { ScaleHeight = true, Cells = { new TableCell(_grid, true) } },
                }
            }
        };
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _totalLabel.TextColor = theme.TextSecondary;
        _chunksLabel.TextColor = theme.TextSecondary;
        _myRankLabel.TextColor = theme.Accent;
    }

    public async Task RefreshAsync()
    {
        try
        {
            var lb = await _api.GetLeaderboardAsync();
            if (lb == null) return;

            Application.Instance.AsyncInvoke(() =>
            {
                _grid.DataStore = lb.Leaderboard;
                _totalLabel.Text = $"Contributors: {lb.TotalContributors}";
                _chunksLabel.Text = $"Total chunks: {lb.TotalChunksGenerated:N0}";
                _myRankLabel.Text = $"{lb.Leaderboard.Count} players";
            });
        }
        catch { }
    }
}
