using ChunkDMesh.Client.Models;
using ChunkDMesh.Client.Services;
using Eto.Forms;
using Eto.Drawing;

namespace ChunkDMesh.Client;

public sealed class MainForm : Form
{
    private readonly AppController _ctrl;
    private readonly TextArea _logBox;
    private readonly Button _startBtn;
    private readonly Button _stopBtn;
    private readonly Label _statusLabel;
    private readonly Label _regionLabel;
    private readonly Label _batchesLabel;
    private readonly Label _pointsLabel;
    private readonly GridView<LeaderboardEntry> _leaderboardGrid;
    private readonly UITimer _leaderboardTimer;
    private readonly UITimer _stateTimer;

    public MainForm()
    {
        Title = "ChunkDMesh Client";
        ClientSize = new Size(900, 650);
        MinimumSize = new Size(700, 500);

        var serverUrl = "http://127.0.0.1:8000";
        _ctrl = new AppController(serverUrl);
        _ctrl.LogMessage += OnLogMessage;
        _ctrl.StateChanged += OnStateChanged;

        _logBox = new TextArea { ReadOnly = true, Height = 200 };

        _startBtn = new Button { Text = "▶ Start" };
        _stopBtn = new Button { Text = "■ Stop", Enabled = false };

        _statusLabel = new Label();
        _regionLabel = new Label();
        _batchesLabel = new Label();
        _pointsLabel = new Label();
        RefreshState();

        _leaderboardGrid = new GridView<LeaderboardEntry>
        {
            Height = 250,
        };
        _leaderboardGrid.Columns.Add(new GridColumn { HeaderText = "#", Width = 40 });
        _leaderboardGrid.Columns.Add(new GridColumn { HeaderText = "Player", Width = 150 });
        _leaderboardGrid.Columns.Add(new GridColumn { HeaderText = "Points", Width = 80 });
        _leaderboardGrid.Columns.Add(new GridColumn { HeaderText = "Regions", Width = 80 });
        _leaderboardGrid.Columns.Add(new GridColumn { HeaderText = "Tier", Width = 50 });

        var tabs = new TabControl
        {
            Pages =
            {
                new TabPage { Text = "Status", Content = BuildStatusTab() },
                new TabPage { Text = "Leaderboard", Content = BuildLeaderboardTab() },
                new TabPage { Text = "Settings", Content = BuildSettingsTab() },
            }
        };

        Content = new StackLayout
        {
            Padding = 10,
            Spacing = 6,
            Items = { tabs }
        };

        _startBtn.Click += async (_, _) => await StartAsync();
        _stopBtn.Click += async (_, _) => await StopAsync();

        _leaderboardTimer = new UITimer { Interval = 10 };
        _leaderboardTimer.Elapsed += async (_, _) => await RefreshLeaderboardAsync();
        _leaderboardTimer.Start();

        _stateTimer = new UITimer { Interval = 1 };
        _stateTimer.Elapsed += (_, _) => RefreshState();
        _stateTimer.Start();

        _ = RestoreSessionAsync();
    }

    private Control BuildStatusTab()
    {
        _startBtn.Size = new Size(100, 32);
        _stopBtn.Size = new Size(100, 32);

        return new StackLayout
        {
            Padding = 10,
            Spacing = 8,
            Items =
            {
                new StackLayout
                {
                    Orientation = Orientation.Horizontal,
                    Spacing = 10,
                    Items = { _startBtn, _stopBtn }
                },
                new StackLayout
                {
                    Orientation = Orientation.Horizontal,
                    Spacing = 20,
                    Items = { _statusLabel, _regionLabel, _batchesLabel, _pointsLabel }
                },
                new Label { Text = "Log:" },
                _logBox,
            }
        };
    }

    private Control BuildLeaderboardTab()
    {
        return new StackLayout
        {
            Padding = 10,
            Spacing = 6,
            Items = { _leaderboardGrid }
        };
    }

    private Control BuildSettingsTab()
    {
        var serverUrlBox = new TextBox { Text = "http://127.0.0.1:8000", Width = 300 };
        var inviteBox = new TextBox { Text = "", Width = 300, PlaceholderText = "Invite code (CHUNK-XXXX-XXXX)" };

        var connectBtn = new Button { Text = "Connect" };
        connectBtn.Click += async (_, _) =>
        {
            var code = inviteBox.Text.Trim();
            if (string.IsNullOrEmpty(code))
            {
                MessageBox.Show("Enter invite code or re-launch with --server", "Connection");
                return;
            }
            await _ctrl.LoginWithInviteAsync(code);
        };

        return new StackLayout
        {
            Padding = 10,
            Spacing = 8,
            Items =
            {
                new Label { Text = "Server URL:" },
                serverUrlBox,
                new Label { Text = "Invite Code:" },
                inviteBox,
                connectBtn,
                new Label { Text = "Auto-configures everything. Leave blank for direct connection.",
                           TextColor = Colors.Gray }
            }
        };
    }

    private async Task StartAsync()
    {
        _startBtn.Enabled = false;
        _stopBtn.Enabled = true;
        _logBox.Text = "";

        try
        {
            await _ctrl.StartAsync();
        }
        catch (Exception ex)
        {
            OnLogMessage($"Error: {ex.Message}");
        }
    }

    private async Task StopAsync()
    {
        await _ctrl.StopAsync();
        _startBtn.Enabled = true;
        _stopBtn.Enabled = false;
        OnLogMessage("Stopped");
    }

    private async Task RestoreSessionAsync()
    {
        var ok = await _ctrl.TryRestoreSessionAsync();
        if (ok)
        {
            OnLogMessage("Session restored");
            RefreshState();
        }
    }

    private void OnLogMessage(string msg)
    {
        Application.Instance.AsyncInvoke(() =>
        {
            _logBox.Text += $"[{DateTime.Now:HH:mm:ss}] {msg}\n";
            _logBox.CaretIndex = _logBox.Text.Length;
        });
    }

    private void OnStateChanged()
    {
        Application.Instance.AsyncInvoke(RefreshState);
    }

    private async Task RefreshLeaderboardAsync()
    {
        try
        {
            var lb = await _ctrl.Api.GetLeaderboardAsync();
            if (lb != null)
            {
                Application.Instance.AsyncInvoke(() =>
                {
                    _leaderboardGrid.DataStore = lb.Leaderboard;
                    _pointsLabel.Text = $"Contributors: {lb.TotalContributors}";
                });
            }
        }
        catch { }
    }

    private void RefreshState()
    {
        _statusLabel.Text = $"Status: {_ctrl.TaskLoop.Status}";
        _regionLabel.Text = $"Region: {_ctrl.TaskLoop.CurrentRegion}";
        _batchesLabel.Text = $"Batches: {_ctrl.TaskLoop.BatchesCompleted}";
        _pointsLabel.Text = $"Chunks: {_ctrl.TaskLoop.TotalChunks}";
    }

    protected override void OnClosed(EventArgs e)
    {
        _leaderboardTimer.Stop();
        _stateTimer.Stop();
        _ctrl.Dispose();
        base.OnClosed(e);
    }
}
