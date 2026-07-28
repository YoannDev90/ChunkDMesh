using ChunkDMesh.Client.Controls;
using ChunkDMesh.Client.Models;
using ChunkDMesh.Client.Services;
using Eto.Drawing;
using Eto.Forms;

namespace ChunkDMesh.Client.Views;

public sealed class PerformanceView : Panel
{
    private readonly MetricsService _metrics;
    private readonly StatCard _cardAvg;
    private readonly StatCard _cardPeak;
    private readonly StatCard _cardTotal;
    private readonly Drawable _chart;
    private ThemeColors _theme = ThemeColors.Dark;

    public PerformanceView(MetricsService metrics)
    {
        _metrics = metrics;

        _cardAvg = new StatCard { LabelText = "Avg Rate", AccentColor = _theme.Accent };
        _cardPeak = new StatCard { LabelText = "Peak Rate", AccentColor = _theme.Warning };
        _cardTotal = new StatCard { LabelText = "This Session", AccentColor = _theme.Success };

        _chart = new Drawable
        {
            Size = new Size(600, 250),
            MinimumSize = new Size(300, 150),
        };
        _chart.Paint += DrawChart;

        _metrics.SampleAdded += _ => Application.Instance.AsyncInvoke(() =>
        {
            RefreshStats();
            _chart.Invalidate();
        });

        BuildLayout();
    }

    private void BuildLayout()
    {
        var headerFont = Fonts.Sans(14, FontStyle.Bold);
        Content = new Scrollable
        {
            Content = new TableLayout
            {
                Padding = new Padding(20),
                Spacing = new Size(0, 16),
                Rows =
                {
                    new TableRow(new Label { Text = "Performance Metrics", Font = headerFont, TextColor = _theme.TextPrimary }),
                    new TableRow(_cardAvg, _cardPeak, _cardTotal),
                    new TableRow(new StackLayout
                    {
                        Orientation = Orientation.Horizontal,
                        Items = { new Label { Text = "Chunk Rate Over Time", Font = Fonts.Sans(11, FontStyle.Bold), TextColor = _theme.TextSecondary } }
                    }),
                    new TableRow { ScaleHeight = true, Cells = { new TableCell(_chart, true) } },
                    new TableRow(new Label { Text = "Stats shown every second. Hover data is sampled from the work loop.", TextColor = _theme.TextMuted, Font = Fonts.Sans(9) }),
                }
            }
        };
    }

    public void ApplyTheme(ThemeColors theme)
    {
        _theme = theme;
        BackgroundColor = theme.BgDark;
        _cardAvg.ApplyTheme(theme);
        _cardPeak.ApplyTheme(theme);
        _cardTotal.ApplyTheme(theme);
    }

    private void RefreshStats()
    {
        var (min, max, avg) = _metrics.GetChunkRateStats();
        _cardAvg.ValueText = $"{avg:F1}";
        _cardAvg.Subtext = $"chunks/sec — min {min:F1}";
        _cardPeak.ValueText = $"{max:F1}";
        _cardPeak.Subtext = "chunks/sec peak";
        _cardTotal.ValueText = _metrics.Uptime.TotalMinutes < 1
            ? "< 1 min"
            : $"{_metrics.Uptime.TotalMinutes:F0} min";
        _cardTotal.Subtext = $"{_metrics.History.Count} samples";

        if (_metrics.History.Count > 1)
        {
            var data = _metrics.History.Select(s => (float)s.ChunksPerSecond).ToArray();
            _cardAvg.SetSparklineData(data);
        }
    }

    private void DrawChart(object? sender, PaintEventArgs e)
    {
        var g = e.Graphics;
        var rect = new RectangleF(PointF.Empty, _chart.Size);
        g.FillRectangle(new SolidBrush(_theme.BgCard), rect);

        var samples = _metrics.History;
        if (samples.Count < 2)
        {
            g.DrawText(Fonts.Sans(12), _theme.TextMuted, 20, rect.Height / 2 - 10, "Collecting data...");
            return;
        }

        var margin = 40f;
        var plotRect = new RectangleF(margin, 10, rect.Width - margin * 2, rect.Height - 20);

        var rates = samples.Select(s => (float)s.ChunksPerSecond).ToArray();
        var maxRate = Math.Max(rates.Max(), 0.1f);
        var stepX = plotRect.Width / (rates.Length - 1);

        // Grid lines
        using var gridPen = new Pen(_theme.Border, 0.5f);
        for (int i = 0; i <= 4; i++)
        {
            var y = plotRect.Top + plotRect.Height * i / 4;
            g.DrawLine(gridPen, plotRect.Left, y, plotRect.Right, y);

            var label = $"{maxRate * (1 - i / 4f):F1}";
            g.DrawText(Fonts.Sans(8), _theme.TextMuted, 2, y - 6, label);
        }

        // X axis labels
        for (int i = 0; i < Math.Min(10, rates.Length); i++)
        {
            var idx = i * rates.Length / Math.Max(10, rates.Length - 1);
            idx = Math.Min(idx, rates.Length - 1);
            var x = plotRect.Left + idx * stepX;
            g.DrawText(Fonts.Sans(8), _theme.TextMuted, x - 10, plotRect.Bottom + 4,
                samples[idx].Timestamp.ToString("HH:mm:ss"));
        }

        // Area fill
        var pts = new PointF[rates.Length];
        for (int i = 0; i < rates.Length; i++)
        {
            pts[i] = new PointF(plotRect.Left + i * stepX,
                plotRect.Bottom - rates[i] / maxRate * plotRect.Height);
        }
        var fillPts = new PointF[rates.Length + 2];
        fillPts[0] = new PointF(pts[0].X, plotRect.Bottom);
        Array.Copy(pts, 0, fillPts, 1, rates.Length);
        fillPts[^1] = new PointF(pts[^1].X, plotRect.Bottom);
        using var fillBrush = new SolidBrush(_theme.ChartFill);
        g.FillPolygon(fillBrush, fillPts);

        // Line
        using var linePen = new Pen(_theme.ChartLine, 1.5f);
        g.DrawLines(linePen, pts);

        // Highlight area labels
        g.DrawText(Fonts.Sans(9), _theme.TextMuted, plotRect.Left, 0,
            $"{rates.Length} samples · max {maxRate:F1} ch/s");
    }
}
