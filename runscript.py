#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author:liping
@time: 2021/03/26
@contact: liping.1@bytedance.com
@software: PyCharm
"""

import json
from connection import RemoteClient
from multiprocessing import Pool, Queue
from collections import defaultdict

q = Queue()


def upload(ip: str, localpath: str, destpath: str) -> None:
    remote = RemoteClient(host=ip)
    remote.sftp_put_file(localpath, destpath)


def put_script(nodes: list, src_script: str, dst_script: str) -> None:
    p = Pool(processes=8)
    for i in nodes:
        p.apply_async(upload, args=(i, src_script, dst_script))
    p.close()
    p.join


def run_ssh(ip: str, dst_script: str) -> ():
    remote = RemoteClient(host=ip)
    cmd = "bash {}".format(dst_script)
    result = remote.execute_commands(cmd)  # result is a return list
    return ip, result


def run_callback(msg: ()) -> None:
    ip, result = msg
    r = defaultdict(list)
    for i in result:
        try:
            b = json.loads(i)
            c = b['check_point']
            r[c].append({"alert_status": b['alert_status'],
                         "check_data": b['check_data']})
        except json.JSONDecodeError as e:
            continue
    q.put({ip: r})


def get_result() -> dict:
    check_result = []
    while not q.empty():
        i = q.get()
        check_result.append(i)
    return {"result": check_result}


def run_check(nodes: [], dst_script: str) -> None:
    p = Pool(processes=8)
    for i in nodes:
        p.apply_async(
            func=run_ssh,
            args=(
                i,
                dst_script),
            callback=run_callback)
    p.close()
    p.join()


def run_script(nodes: [], src_script: str, dst_script: str) -> dict:
    put_script(nodes, src_script, dst_script)
    run_check(nodes, dst_script)
    c = get_result()
    return c
