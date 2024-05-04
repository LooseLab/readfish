import numpy as np

WINDSOR_THRESHOLD = 4
SMOOTHING = 400
SIGNAL_THRESHOLD_TOP = 2.2
SIGNAL_THRESHOLD_BOTTOM = 1.5
TROUGH_THRESHOLD = 1000

def uniform_filter(data, size):
  weights = np.ones(size) / size
  smoothed_data = np.convolve(data, weights, mode='same') 
  return smoothed_data

def call_poly_a(signal):
    if len(signal) >= 1000:
        znorm_data = (signal - np.mean(signal[:1000])) / np.std(signal[:1000])
        windsorized_data = np.clip(znorm_data, -WINDSOR_THRESHOLD, WINDSOR_THRESHOLD)
        smoothed_data = uniform_filter(windsorized_data, size=SMOOTHING)
        intersections = np.logical_and(smoothed_data > SIGNAL_THRESHOLD_BOTTOM, smoothed_data < SIGNAL_THRESHOLD_TOP)
        rising_edges = np.where(np.logical_and(intersections[:-1] == False, intersections[1:] == True))[0]
        peaks = rising_edges + 1
        
        return peaks[0] if len(peaks) >= 1  else None, peaks[1] if len(peaks) >= 2 else None
    return None, None