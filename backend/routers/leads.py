from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_leads():
    # TODO: implement lead listing with filters, pagination, search
    return {"message": "router working"}
