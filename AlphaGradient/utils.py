# -*- coding: utf-8 -*-
"""Standard utility functions used throughout the package"""

# Standard imports
from datetime import datetime, date, time, timedelta
import math

# Third Party imports
import pandas as pd

# Local Imports

def deconstruct_dt(dt):
    d = ["year", "month", "day"]
    t = ["hour", "minute", "second", "microsecond"]
    attrs = []

    if isinstance(dt, datetime):
        attrs = d + t
    elif isinstance(dt, time):
        attrs = t
    elif isinstance(dt, date):
        attrs = d
    else:
        raise TypeError(f"{dt=} is not a valid datetime object")

    dtdict = {}
    for attr in attrs:
        dtdict[attr] = getattr(dt, attr)

    return dtdict

def read_timestring(timestring, dtype=time):
    try:
        ampm = "AM"
        info = ""
        timestring = timestring.split(' ')
        if len(timestring) > 1:
            ampm = timestring[1]
        info = timestring[0]
        info = info.split(':')
        if len(info) > 4:
            raise ValueError
        dtdict = {}
        attrs = ["hour", "minute", "second", "microsecond"]
        for attr, value in zip(attrs, info):
            dtdict[attr] = int(value)

        if ampm == "PM":
            dtdict["hour"] = dtdict["hour"] + 12

        for attr in attrs[1:]:
            if not dtdict.get(attr):
                dtdict[attr] = 0

        if dtype is time:
            return time(**dtdict)
        else:
            return dtdict

    except (KeyError, ValueError, TypeError, AttributeError) as e:
            raise ValueError(f"Unable to convert timestring {timestring[0].__repr__()} to time object. Please follow the format: \'HH:MM:SS AM\'") from e


def set_time(dt, t):
    newtime = None
    if isinstance(t, str):
        newtime = read_timestring(t, dtype=dict)
    elif isinstance(t, time):
        newtime = deconstruct_dt(t)
    elif isinstance(t, (datetime, pd.Timestamp, np.datetime64)):
        newtime = deconstruct_dt(t.time())
    else:
        raise TypeError(f"{t=} could not be parsed into a time object")
    if isinstance(dt, datetime):
        return dt.replace(**newtime)
    else:
        try:
            dt = pd.to_datetime(dt)
            return dt.replace(**newtime)
        except Exception:
            raise TypeError(f"dt input must be a datetime. Received {dt=}")


def get_time(t):
    if isinstance(t, str):
        t = read_timestring(t)
    elif isinstance(t, datetime, pd.Timestamp):
        t = t.time()

    if not isinstance(t, time):
        raise ValueError(f"Unable to convert {t=} to time object")
    return t


def timestring(t):
    ampm = "AM"
    hour = t.hour
    minute = t.minute if t.minute > 9 else f"0{t.minute}"
    if hour > 12:
        ampm = "PM"
        hour -= 12
    return f"{hour}:{minute} {ampm}"

def get_weekday(dt):
    weekdays = {0: "Monday",
                1: "Tuesday",
                2: "Wednesday",
                3: "Thursday",
                4: "Friday",
                5: "Saturday",
                6: "Sunday",}

    return weekdays[dt.weekday()]

def progress_print(to_print, last=[0]):
    print("\r" + (" " * last[0]), end="\r", flush=True)
    print(to_print, end="", flush=True)
    last[0] = len(str(to_print))

def isiter(obj):
    try:
        iter(obj)
        return True
    except TypeError:
        return False

def get_batches(iterable, size=100):
    i = 0
    last = len(iterable)
    for i in range(math.ceil(len(iterable) / size)):
        start = i * size
        end = start + size
        end = end if end < last else last
        yield iterable[start:end]

def auto_batch_size(iterable):
    if len(iterable) > 10000:
        return 100
    else:
        return int((-1 * (len(iterable) - 10000) ** 2) * (70 / 100_000_000) + 100)

def auto_batch(iterable):
    return get_batches(iterable, auto_batch_size(iterable))

