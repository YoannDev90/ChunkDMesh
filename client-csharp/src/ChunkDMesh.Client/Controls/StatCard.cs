using Eto.Drawing;
using Eto.Forms;
using ChunkDMesh.Client.Models;

namespace ChunkDMesh.Client.Controls;

public sealed class StatCard : Drawable
{
    private string _label = "";
    private string _value = "--";
    private string _subtext = "";
    private Color _accent;
    private Color _bgCard;
    private Color _textPrimary;
    private Color _textSecondary;
    private Color _textMuted;
    private bool _showSparkline;
    private float[]? _sparklineData;

    public StatCard()
    {
        Size = new Size(220, 120);
        _accent = Colors.DodgerBlue;
        ApplyTheme(ThemeColors.Dark);
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _bgCard = theme.BgCard;
        _textPrimary = theme.TextPrimary;
        _textSecondary = theme.TextSecondary;
        _textMuted = theme.TextMuted;
        _accent = theme.Accent;
        Invalidate();
    }

    public string LabelText
    {
        get => _label;
        set { _label = value; Invalidate(); }
    }

    public string ValueText
    {
        get => _value;
        set { _value = value; Invalidate(); }
    }

    public string Subtext
    {
        get => _subtext;
        set { _subtext = value; Invalidate(); }
    }

    public Color AccentColor
    {
        get => _accent;
        set { _accent = value; Invalidate(); }
    }

    public bool ShowSparkline
    {
        get => _showSparkline;
        set { _showSparkline = value; Invalidate(); }
    }

    public void SetSparklineData(float[] data)
    {
        _sparklineData = data;
        _showSparkline = true;
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        var rect = new RectangleF(PointF.Empty, Size);

        // Card background with rounded corners
        DrawRoundedRect(g, new RectangleF(rect.X + 1, rect.Y + 1, rect.Width - 2, rect.Height - 2), _bgCard, 8);

        // Accent bar at top
        g.FillRectangle(new SolidBrush(_accent), new RectangleF(2, 2, rect.Width - 4, 3));

        // Label
        var labelFont = Fonts.Sans(10);
        g.DrawText(labelFont, _textMuted, 14, 14, _label);

        // Value
        var valueFont = Fonts.Sans(28, FontStyle.Bold);
        if (_showSparkline && _sparklineData is { Length: > 1 })
        {
            var valueRight = rect.Width - 80;
            g.DrawText(valueFont, _textPrimary, 14, 32, _value);

            // Mini sparkline
            DrawSparkline(g, _sparklineData,
                new RectangleF(valueRight, 36, rect.Width - valueRight - 12, 36));
        }
        else
        {
            g.DrawText(valueFont, _textPrimary, 14, 32, _value);
        }

        // Subtext
        if (!string.IsNullOrEmpty(_subtext))
        {
            g.DrawText(labelFont, _textSecondary, 14, 72, _subtext);
        }
    }

    private static void DrawRoundedRect(Graphics g, RectangleF rect, Color color, float radius)
    {
        using var brush = new SolidBrush(color);
        var path = new GraphicsPath();
        path.AddRectangle(rect);
        g.FillPath(brush, path);
    }

    private void DrawSparkline(Graphics g, float[] data, RectangleF rect)
    {
        if (data.Length < 2) return;

        var min = data.Min();
        var max = data.Max();
        var range = Math.Max(max - min, 0.001f);
        var stepX = rect.Width / (data.Length - 1);

        var pts = new PointF[data.Length];
        for (int i = 0; i < data.Length; i++)
        {
            var y = rect.Bottom - ((data[i] - min) / range) * rect.Height;
            pts[i] = new PointF(rect.X + i * stepX, y);
        }

        // Fill
        var fillPts = new PointF[data.Length + 2];
        fillPts[0] = new PointF(pts[0].X, rect.Bottom);
        Array.Copy(pts, 0, fillPts, 1, data.Length);
        fillPts[^1] = new PointF(pts[^1].X, rect.Bottom);

        using var fillBrush = new SolidBrush(_chartFill);
        g.FillPolygon(fillBrush, fillPts);

        // Line
        using var pen = new Pen(_accent, 1.5f);
        g.DrawLines(pen, pts);
    }

    private Color _chartFill = Color.FromArgb(99, 102, 241, 40);
}
