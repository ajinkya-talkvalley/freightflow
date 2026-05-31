from django.urls import path

from . import views

app_name = 'ai_assistant'

urlpatterns = [
    path('', views.assistant, name='assistant'),
]
