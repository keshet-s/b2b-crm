from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_activities():
    # TODO: implement activity feed listing and creation endpoints
    return {"message": "router working"}
