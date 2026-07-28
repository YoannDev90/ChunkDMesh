using ChunkDMesh.Client.Models;
using ChunkDMesh.Client.Services;
using Eto.Drawing;
using Eto.Forms;

namespace ChunkDMesh.Client.Views;

public sealed class SettingsView : Panel
{
    private readonly AppController _ctrl;
    private readonly TextBox _serverBox;
    private readonly TextBox _inviteBox;
    private readonly DropDown _themeSelect;
    private readonly Label _versionLabel;
    private ThemeColors _theme = ThemeColors.Dark;

    public event Action<ThemeColors>? ThemeChanged;

    public SettingsView(AppController ctrl)
    {
        _ctrl = ctrl;

        _serverBox = new TextBox { Text = "http://127.0.0.1:8000", Width = 350 };
        _inviteBox = new TextBox { Width = 350, PlaceholderText = "CHUNK-XXXX-XXXX" };

        _themeSelect = new DropDown
        {
            Width = 200,
            Items = { "Dark", "Light" },
            SelectedIndex = 0,
        };

        _versionLabel = new Label
        {
            Text = "ChunkDMesh Client v0.1.0 — Eto.Forms",
            TextColor = _theme.TextMuted,
            Font = Fonts.Sans(9),
        };

        BuildLayout();

        _themeSelect.SelectedIndexChanged += (_, _) =>
        {
            var theme = _themeSelect.SelectedIndex == 0 ? ThemeColors.Dark : ThemeColors.Light;
            ThemeChanged?.Invoke(theme);
        };
    }

    private void BuildLayout()
    {
        var headerFont = Fonts.Sans(14, FontStyle.Bold);
        var sectionFont = Fonts.Sans(11, FontStyle.Bold);

        Content = new Scrollable
        {
            Content = new TableLayout
            {
                Padding = new Padding(20),
                Spacing = new Size(0, 16),
                Rows =
                {
                    new TableRow(new Label { Text = "Settings", Font = headerFont, TextColor = _theme.TextPrimary }),

                    new TableRow(new Label { Text = "SERVER CONNECTION", Font = sectionFont, TextColor = _theme.Accent }),
                    new TableRow(CreateField("Server URL", _serverBox)),
                    new TableRow(CreateField("Invite Code", _inviteBox)),
                    new TableRow(
                        new Button { Text = "Connect" }.WithClick(async (_, _) =>
                        {
                            var code = _inviteBox.Text.Trim();
                            if (!string.IsNullOrEmpty(code))
                                await _ctrl.LoginWithInviteAsync(code);
                            else
                                MessageBox.Show("Enter invite code first", "Connection");
                        }),
                        new Button { Text = "Restore Session" }.WithClick(async (_, _) =>
                        {
                            var ok = await _ctrl.TryRestoreSessionAsync();
                            MessageBox.Show(ok ? "Session restored" : "No saved session", "Auth");
                        }),
                        new Button { Text = "Logout" }.WithClick((_, _) =>
                        {
                            _ctrl.Auth.Logout();
                            MessageBox.Show("Logged out", "Auth");
                        })
                    ),

                    new TableRow(new Label { Text = "APPEARANCE", Font = sectionFont, TextColor = _theme.Accent }),
                    new TableRow(CreateField("Theme", _themeSelect)),

                    new TableRow(new Label { Text = "ABOUT", Font = sectionFont, TextColor = _theme.Accent }),
                    new TableRow(_versionLabel),
                    new TableRow(new Label { Text = "Distributed Minecraft world pre-generation.",
                               TextColor = _theme.TextMuted, Font = Fonts.Sans(9) }),
                }
            }
        };
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _versionLabel.TextColor = theme.TextMuted;
    }

    private static Control CreateField(string label, Control input)
    {
        return new StackLayout
        {
            Orientation = Orientation.Horizontal,
            Spacing = 10,
            VerticalContentAlignment = VerticalAlignment.Center,
            Items =
            {
                new Label { Text = label, Width = 110 },
                input,
            }
        };
    }
}

internal static class ButtonExtensions
{
    public static Button WithClick(this Button btn, EventHandler<EventArgs> handler)
    {
        btn.Click += handler;
        return btn;
    }
}
