from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
import httpx

from nbp_pipeline.ingest import ingest_range
from nbp_pipeline.state import advance_watermark. read_watermark

