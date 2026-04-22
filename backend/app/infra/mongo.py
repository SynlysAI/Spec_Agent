"""MongoDB 连接与集合访问模块。"""

from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.core.config import settings


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    """获取 MongoDB 客户端单例。

    函数名称: get_mongo_client
    参数说明:
    - 无。
    """
    return MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)


def get_database() -> Database:
    """获取业务数据库对象。

    函数名称: get_database
    参数说明:
    - 无。
    """
    return get_mongo_client()[settings.mongodb_database]


def get_tasks_collection() -> Collection:
    """获取 tasks 集合。

    函数名称: get_tasks_collection
    参数说明:
    - 无。
    """
    return get_database()["tasks"]


def get_results_collection() -> Collection:
    """获取 analysis_results 集合。

    函数名称: get_results_collection
    参数说明:
    - 无。
    """
    return get_database()["analysis_results"]


def get_files_collection() -> Collection:
    """获取 files 集合。

    函数名称: get_files_collection
    参数说明:
    - 无。
    """
    return get_database()["files"]


def get_acceptance_runs_collection() -> Collection:
    """获取 acceptance_runs 集合。

    函数名称: get_acceptance_runs_collection
    参数说明:
    - 无。
    """
    return get_database()["acceptance_runs"]


def get_lab_collect_runs_collection() -> Collection:
    """获取 lab_collect_runs 集合。

    函数名称: get_lab_collect_runs_collection
    参数说明:
    - 无。
    """
    return get_database()["lab_collect_runs"]


def get_spectrum_samples_collection() -> Collection:
    """获取 spectrum_samples 集合。

    函数名称: get_spectrum_samples_collection
    参数说明:
    - 无。
    """
    return get_database()["spectrum_samples"]


def get_spectrum_sample_files_collection() -> Collection:
    """获取 spectrum_sample_files 集合。

    函数名称: get_spectrum_sample_files_collection
    参数说明:
    - 无。
    """
    return get_database()["spectrum_sample_files"]


def get_molecular_statistics_collection() -> Collection:
    """获取 molecular_statistics_cache 集合。

    函数名称: get_molecular_statistics_collection
    参数说明:
    - 无。
    """
    return get_database()["molecular_statistics_cache"]
