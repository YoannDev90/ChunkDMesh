using Eto.Drawing;
using Eto.Forms;
using ChunkDMesh.Client.Models;

namespace ChunkDMesh.Client.Controls;

public sealed class ActivityFeed : Drawable
{
    private readonly List<ActivityEntry> _entries = [];
    private ThemeColors _theme = ThemeColors.Dark;

    public ActivityFeed()
    {
        Size = new Size(400, 300);
        MinimumSize = new Size(200, 100);
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        Invalidate();
    }

    public void AddEntry(string icon, string message, Color? accent = null)
    {
        _entries.Add(new ActivityEntry
        {
            Icon = icon,
            Message = message,
            Timestamp = DateTime.Now,
            Accent = accent ?? _theme.Accent,
        });

        if (_entries.Count > 50)
            _entries.RemoveAt(0);

        // Auto-scroll: keep last entries visible
        Invalidate();
    }

    public void Clear()
    {
        _entries.Clear();
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;

        // Background
        g.FillRectangle(new SolidBrush(_theme.BgCard), new RectangleF(PointF.Empty, Size));

        var y = 6f;
        var entryHeight = 28f;
        var maxVisible = (int)(Size.Height / entryHeight) - 1;
        var startIdx = Math.Max(0, _entries.Count - maxVisible);

        var tsFont = Fonts.Sans(8);
        var msgFont = Fonts.Sans(10);

        for (int i = startIdx; i < _entries.Count; i++)
        {
            var e2 = _entries[i];
            if (y + entryHeight > Size.Height) break;

            // Accent dot
            g.FillEllipse(new SolidBrush(e2.Accent), 10, y + 4, 6, 6);

            // Icon
            g.DrawText(msgFont, _theme.TextMuted, 22, y, e2.Icon);

            // Message
            g.DrawText(msgFont, _theme.TextSecondary, 42, y, e2.Message);

            // Timestamp
            var ts = e2.Timestamp.ToString("HH:mm:ss");
            var tw = tsFont.MeasureString(ts).Width;
            g.DrawText(tsFont, _theme.TextMuted, Size.Width - tw - 10, y, ts);

            y += entryHeight;
        }

        if (_entries.Count == 0)
        {
            g.DrawText(msgFont, _theme.TextMuted, 14, 10, "No activity yet...");
        }
    }

    private sealed record ActivityEntry
    {
        public string Icon { get; init; } = "";
        public string Message { get; init; } = "";
        public DateTime Timestamp { get; init; }
        public Color Accent { get; init; }
    }
}
