from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_sourcing_runs():
    # TODO: implement sourcing run history and trigger endpoint
    return {"message": "router working"}
