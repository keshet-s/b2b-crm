from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_companies():
    # TODO: implement company listing with filters and pagination
    return {"message": "router working"}
