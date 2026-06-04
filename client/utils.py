import os
import psutil

class ResourceReportFormat:
    DETAILED = "detailed"
    VALUE = "value"

def get_available_resources_averaged(print_output=False, return_format=ResourceReportFormat.DETAILED):
    """Ressources disponibles avec fréquence CPU et utilisation RAM/CPU"""
    
    load_avg = psutil.getloadavg()
    num_cores = os.cpu_count()
    
    cpu_freq = psutil.cpu_freq()
    freq_current = cpu_freq.current / 1000
    freq_max = cpu_freq.max / 1000
    
    cpu_used_pct = min(100, (load_avg[1] / num_cores) * 100)
    cpu_available_pct = 100 - cpu_used_pct
    
    ram_info = psutil.virtual_memory()
    ram_total = ram_info.total / (1024**3)
    ram_available = ram_info.available / (1024**3)
    ram_used_pct = ram_info.percent
    ram_available_pct = 100 - ram_used_pct

    # Composed score: frequency * cores * available CPU * available RAM
    cpu_power = freq_current * num_cores * (cpu_available_pct / 100)
    ram_power = ram_available * (ram_available_pct / 100)
    power_available = cpu_power * (ram_power / ram_total)
    
    if print_output:
        print(f"=== CPU ===")
        print(f"Load average (1/5/15 min): {load_avg[0]:.2f} / {load_avg[1]:.2f} / {load_avg[2]:.2f}")
        print(f"Frequency: {freq_current:.1f} GHz / {freq_max:.1f} GHz (max)")
        print(f"Cores: {num_cores}")
        print(f"Usage (avg 5min): {cpu_used_pct:.1f}%")
        print(f"CPU available: {cpu_available_pct:.1f}%")
        print(f"\n=== RAM ===")
        print(f"Total: {ram_total:.1f} Go")
        print(f"Available: {ram_available:.1f} Go")
        print(f"Usage: {ram_used_pct:.1f}%")
        print(f"RAM available: {ram_available_pct:.1f}%")
        print(f"\n=== SCORE ===")
        print(f"Available CPU power: {cpu_power:.2f}")
        print(f"Available RAM power: {ram_power:.2f} Go")
        print(f"Total power score: {power_available:.2f}")

    infos = {
        'load_avg_5min': load_avg[1],
        'cpu_freq_ghz': freq_current,
        'cpu_available_pct': cpu_available_pct,
        'cpu_power': cpu_power,
        'ram_available_gb': ram_available,
        'ram_available_pct': ram_available_pct,
        'ram_power': ram_power,
        'power_score': power_available
    } if return_format == ResourceReportFormat.DETAILED else power_available
    
    return infos