from fastapi import APIRouter, HTTPException
from algorithms.registry import list_algos, get_algo
from api.schemas import AlgoInfo

router = APIRouter(tags=["algorithms"])


@router.get("/algorithms", response_model=list[AlgoInfo])
def get_algorithms():
    return [
        AlgoInfo(
            name=a.name,
            display_name=a.display_name,
            required_tfs=a.required_tfs,
            exec_tf=a.exec_tf,
            needs_fit=a.needs_fit,
            description=a.description,
            indicator_keys=a.indicator_keys,
        )
        for a in list_algos()
    ]


@router.get("/algorithms/{name}", response_model=AlgoInfo)
def get_algorithm(name: str):
    a = get_algo(name)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Algorithm '{name}' not found")
    return AlgoInfo(
        name=a.name,
        display_name=a.display_name,
        required_tfs=a.required_tfs,
        exec_tf=a.exec_tf,
        needs_fit=a.needs_fit,
        description=a.description,
        indicator_keys=a.indicator_keys,
    )
