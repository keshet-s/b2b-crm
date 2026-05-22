from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def scoring_status():
    # TODO: implement ICP scoring trigger and results endpoints
    return {"message": "router working"}
