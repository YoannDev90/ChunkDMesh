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
    private Label _pageTitle;
    private Label _versionLabel;
    private ThemeColors _theme = ThemeColors.Dark;

    public event Action<ThemeColors>? ThemeChanged;

    public SettingsView(AppController ctrl)
    {
        _ctrl = ctrl;

        _serverBox = new TextBox { Text = "http://127.0.0.1:8000", Width = 350, BackgroundColor = _theme.BgInput, TextColor = _theme.TextPrimary, Font = Fonts.Sans(11) };
        _inviteBox = new TextBox { Width = 350, PlaceholderText = "CHUNK-XXXX-XXXX", BackgroundColor = _theme.BgInput, TextColor = _theme.TextPrimary, Font = Fonts.Sans(11) };

        _themeSelect = new DropDown
        {
            Width = 200,
            Items = { "🌙 Dark", "☀️ Light" },
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
        var headerFont = Fonts.Sans(18, FontStyle.Bold);
        var sectionFont = Fonts.Sans(11, FontStyle.Bold);

        _pageTitle = new Label
        {
            Text = "Settings",
            Font = headerFont,
            TextColor = _theme.TextPrimary,
        };

        var content = new StackLayout
        {
            Padding = new Padding(20, 12),
            Spacing = 16,
            Items =
            {
                _pageTitle,

                new StackLayoutItem(new Label { Text = "SERVER CONNECTION", Font = sectionFont, TextColor = _theme.Accent }, false),
                CreateField("Server URL", _serverBox),
                CreateField("Invite Code", _inviteBox),
                new StackLayout
                {
                    Orientation = Orientation.Horizontal,
                    Spacing = 8,
                    Items =
                    {
                        CreateStyledButton("Connect", _theme.Accent, async (_, _) =>
                        {
                            var code = _inviteBox.Text.Trim();
                            if (string.IsNullOrEmpty(code))
                            {
                                MessageBox.Show("Enter an invite code or leave blank for direct connect", "Connection");
                                return;
                            }
                            if (!IsValidInviteCode(code))
                            {
                                MessageBox.Show("Invite code format: CHUNK-XXXX-XXXX", "Invalid Format");
                                return;
                            }
                            await _ctrl.LoginWithInviteAsync(code);
                        }),
                        CreateStyledButton("Restore Session", _theme.Border, async (_, _) =>
                        {
                            var ok = await _ctrl.TryRestoreSessionAsync();
                            MessageBox.Show(ok ? "Session restored" : "No saved session found", "Auth");
                        }),
                        CreateStyledButton("Logout", _theme.Danger, (_, _) =>
                        {
                            var result = MessageBox.Show(this, "Log out of current session?", "Confirm Logout",
                                MessageBoxButtons.YesNo, MessageBoxType.Warning);
                            if (result == DialogResult.Yes)
                            {
                                _ctrl.Auth.Logout();
                                MessageBox.Show("Logged out", "Auth");
                            }
                        }),
                    }
                },

                new StackLayoutItem(new Label { Text = "APPEARANCE", Font = sectionFont, TextColor = _theme.Accent }, false),
                CreateField("Theme", _themeSelect),

                new StackLayoutItem(new Label { Text = "ABOUT", Font = sectionFont, TextColor = _theme.Accent }, false),
                _versionLabel,
                new Label { Text = "Distributed Minecraft world pre-generation engine.", TextColor = _theme.TextMuted, Font = Fonts.Sans(9) },
            }
        };

        Content = new Scrollable { Content = content };
    }

    private static StackLayout CreateField(string label, Control input)
    {
        return new StackLayout
        {
            Orientation = Orientation.Horizontal,
            Spacing = 10,
            VerticalContentAlignment = VerticalAlignment.Center,
            Items =
            {
                new Label { Text = label, Width = 120, Font = Fonts.Sans(11) },
                input,
            }
        };
    }

    private static Button CreateStyledButton(string text, Color bgColor, EventHandler<EventArgs> handler)
    {
        var btn = new Button { Text = text, Font = Fonts.Sans(11) };
        btn.BackgroundColor = bgColor;
        btn.TextColor = Color.FromArgb(255, 255, 255);
        btn.Size = new Size(120, 32);
        btn.Click += handler;
        return btn;
    }

    private static bool IsValidInviteCode(string code)
    {
        return System.Text.RegularExpressions.Regex.IsMatch(code, @"^CHUNK-[A-Z0-9]{4}-[A-Z0-9]{4}$");
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _pageTitle.TextColor = theme.TextPrimary;
        _versionLabel.TextColor = theme.TextMuted;
        _themeSelect.BackgroundColor = theme.BgInput;
        _themeSelect.TextColor = theme.TextPrimary;
        _serverBox.BackgroundColor = theme.BgInput;
        _serverBox.TextColor = theme.TextPrimary;
        _inviteBox.BackgroundColor = theme.BgInput;
        _inviteBox.TextColor = theme.TextPrimary;
    }
}