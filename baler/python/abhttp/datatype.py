import logging
import collections
import copy
import StringIO
import time
import calendar
import re
from datetime import datetime
from dateutil import tz

logger = logging.getLogger(__name__)

class Slots(object):
    """Slots is a based class for MUTABLE named tuple.

    For IMmutable named tuple, please use collections.namedtuple class factory.
    Iterator for Slots shall behave like iterator for tuple (yielding values),
    not dict (yielding keys).
    """
    __slots__ = []

    def __init__(self):
        print "Slots!!"
        del self.__hash__

    def __hash__(self):
        raise TypeError("Mutable object shall not be hashed!")

    def __str__(self):
        return " ".join([str(getattr(self, a)) for a in self.__slots__ ])

    def __cmp__(self, other):
        if other == None:
            return -1 # None is the greatest .. this is good for min-heap.
        if type(other) != type(self):
            return -1
        for a in self.__slots__:
            x = getattr(self, a)
            y = getattr(other, a)
            if x < y:
                return -1
            if x > y:
                return 1
        return 0

    def __getstate__(self):
        return [getattr(self, a) for a in self.__slots__]

    def __setstate__(self, state):
        # state is the state from self.__getstate__()
        i = 0
        for a in self.__slots__:
            setattr(self, a, state[i])
            i += 1

    def __iter__(self):
        for a in self.__slots__:
            x = getattr(self, a)
            yield x

    def items(self):
        """Iterator yielding key,value pair."""
        for a in self.__slots__:
            x = getattr(self, a)
            yield (a, x)


class Host(Slots):
    """Host data representation."""

    __slots__ = ['host_id', 'text']

    def __init__(self, host_id, text):
        self.host_id = host_id
        self.text = text

    def __str__(self):
        return self.text

TZ_LOCAL = tz.tzlocal()

def sign(num):
    if num < 0:
        return -1
    return 1

class Timestamp(collections.namedtuple("Timestamp", ["sec", "usec"])):
    TS_REGEX = re.compile("(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d):(\d\d)(?:\.(\d{6}))?(?:([+-]\d\d):(\d\d))?")
    @staticmethod
    def fromJSONObj(jobj):
        return Timestamp(long(jobj["sec"]), int(jobj["usec"]))

    @staticmethod
    def fromStr(s):
        m = Timestamp.TS_REGEX.match(s)
        if not m:
            raise ValueError("Invalid format")
        (y,m,d,H,M,S,u,zh,zm) = (int(x) if x!=None else None for x in m.groups())
        if zh == None:
            # Unknown target timezone, treat as local time
            ts_sec = time.mktime((y,m,d,H,M,S,0,0,-1))
        else:
            ts_sec = calendar.timegm((y,m,d,H,M,S))
            zh = int(zh)
            zm = sign(zh)*int(zm)
            ts_sec -= zh*3600 + zm*60
        if u:
            ts_usec = int(u)
        else:
            ts_usec = 0
        return Timestamp(ts_sec, ts_usec)

    def my_fmt(self):
        tm = time.localtime(self.sec)
        if tm.tm_isdst:
            tzsec = time.altzone
        else:
            tzsec = time.timezone
        # NOTE: Apparently time.timezone is #sec to UTC, i.e. CST is 21600
        tz_hr = -sign(tzsec)*abs(tzsec)/3600
        tz_min = (abs(tzsec) % 3600)/60
        s = "%d-%02d-%02dT%02d:%02d:%02d.%06d%+03d:%02d" % (
                tm.tm_year,
                tm.tm_mon,
                tm.tm_mday,
                tm.tm_hour,
                tm.tm_min,
                tm.tm_sec,
                self.usec,
                tz_hr,
                tz_min
        )
        return s

    def dt_fmt(self):
        global TZ_LOCAL
        dt = datetime.fromtimestamp(self.sec, tz=TZ_LOCAL)
        return dt.isoformat()

    def __str__(self):
        return self.my_fmt()


class Token(collections.namedtuple("Token", ["tok_type", "text"])):
    @staticmethod
    def fromJSONObj(jobj):
        return Token(jobj["tok_type"], jobj["text"])

    def __str__(self):
        return self.text


class LogMessage(Slots):
    """Log message representation."""

    __slots__ = ["ts", "host", "msg", "pos", "ptn_id"]

    def __init__(self, ts=None, host=None, msg=None, pos=None, ptn_id=None):
        self.ts = ts
        self.host = host
        self.msg = msg
        self.pos = pos
        self.ptn_id = ptn_id

    def __str__(self):
        s = "".join(str(x) for x in self.msg)
        return " ".join([str(x) for x in [self.ts, self.host, s]])

    @staticmethod
    def fromJSONObj(jobj):
        msg = [Token.fromJSONObj(x) for x in jobj["msg"]]
        if "pos" in jobj:
            pos = jobj["pos"]
        else:
            pos = None
        jts = jobj["ts"]
        ts = Timestamp(jts["sec"], jts["usec"])
        if "ptn_id" in jobj:
            ptn_id = jobj["ptn_id"]
        else:
            ptn_id = None
        return LogMessage(ts, jobj["host"], msg, pos, ptn_id)

    def text(self):
        return "".join([str(x) for x in self.msg])

    def __cmp__(self, other):
        if other == None:
            return -1
        return super(LogMessage, self).__cmp__(other)


PixelKey = collections.namedtuple("PixelKey", ["ptn_id", "sec", "comp_id"])

class Pattern(Slots):
    """Object (mutable) representing baler pattern."""

    __slots__ = ["ptn_id", "count", "first_seen", "last_seen", "text"]

    def __init__(self, ptn_id, count, first_seen, last_seen, text):
        self.ptn_id = ptn_id
        self.count = count
        self.first_seen = first_seen
        self.last_seen = last_seen
        self.text = text

    @staticmethod
    def fromJSONObj(jobj):
        ptn_id = jobj["ptn_id"]
        count = jobj["count"]
        first_seen = jobj["first_seen"]
        last_seen = jobj["last_seen"]
        text = "".join(x["text"] for x in jobj["msg"])
        return Pattern(ptn_id, count, first_seen, last_seen, text)

    def __str__(self):
        return "%s %s %s %s %s" % (
                    self.ptn_id,
                    self.count,
                    self.first_seen,
                    self.last_seen,
                    self.text
                )

    def __add__(self, other):
        p = self.copy()
        p += other
        return p

    def __radd__(self, other):
        return self + other

    def __iadd__(self, other):
        """Merge ``other`` information into ``self``.

        ``self.ptn_id`` will stay the same.
        ``self.count`` will increase by ``other.count``.
        ``self.first_seen`` will be the minimum of ``self.first_seen`` and
                ``other.first_seen``.
        ``self.last_seen`` will be the maximum of ``self.last_seen`` and
                ``other.last_seen``.
        ``self.text`` will the same.

        Raises:
            ValueError: if ``other.text`` is not the same as ``self.text``.
        """
        if other == None:
            return self
        if self.text != other.text:
            raise ValueError("merging incompatible patterns.")
        self.count += other.count
        first_seen = min(self.first_seen, other.first_seen)
        if first_seen == None: # None is always the minimum
            first_seen = max(self.first_seen, other.first_seen)
        self.first_seen = first_seen
        self.last_seen = max(self.last_seen, other.last_seen)
        return self

    def __eq__(self, other):
        if other == None:
            return False
        return (self.ptn_id == other.ptn_id and
               self.count == other.count and
               self.first_seen == other.first_seen and
               self.last_seen == other.last_seen and
               self.text == other.text)

    def __neq__(self, other):
        return not self.__eq__(other)

    def __req__(self, other):
        return self == other

    def copy(self):
        return copy.copy(self)


class Pixel(Slots):
    """Object representing baler image pixel."""

    __slots__ = ["key", "count"]

    def __init__(self, sec, comp_id, ptn_id, count):
        self.key = PixelKey(ptn_id=ptn_id, sec=sec, comp_id=comp_id)
        self.count = count

    def __str__(self):
        return ", ".join([
                        str(x) for x in [
                            self.key.ptn_id,
                            self.key.sec,
                            self.key.comp_id,
                            self.count,
                        ]
                    ])

    def __repr__(self):
        return "abhttp.Pixel(sec=%d, comp_id=%d, ptn_id=%d, count=%d)" % (
                    self.key.sec, self.key.comp_id, self.key.ptn_id, self.count
                )


class IDSet(set):
    def __init__(self, obj=None):
        super(IDSet, self).__init__()
        if obj != None:
            self.add_smart(obj)

    def add_number(self, num):
        self.add(num)

    def add_numbers(self, iterable):
        for x in iterable:
            self.add(x)

    def add_csv(self, csv=str()):
        for s in csv.split(','):
            t = s.split("-")
            x0 = int(t[0])
            x1 = x0
            if len(t) > 1:
                x1 = int(t[1])
            for i in xrange(x0, x1+1):
                self.add(i)

    def add_smart(self, obj):
        if type(obj) == str:
            return self.add_csv(obj)
        try:
            # first, try iterable
            for x in obj:
                self.add_smart(x)
        except TypeError:
            # if failed, try single number
            self.add_number(obj)

    def to_csv(self):
        s = [x for x in iter(self)]
        s.sort()
        prev = None
        sio = StringIO.StringIO()
        rflag = False
        for x in s:
            if prev == None:
                # this is the first item
                sio.write(str(x))
                prev = x
                continue
            if x - prev > 1:
                if rflag:
                    sio.write("-%d" % prev)
                    rflag = False
                sio.write(",%d" % x)
            else:
                rflag = True
            prev = x
        if rflag:
            sio.write("-%d" % prev)
            rflag = False
        ret = sio.getvalue()
        sio.close()
        return ret
