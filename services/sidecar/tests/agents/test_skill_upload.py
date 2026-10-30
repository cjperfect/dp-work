import asyncio
import io
import zipfile
import pytest
from src import config
from src.skills import service

SKILL=b'---\nname: department-sop\ndescription: Department workflow\n---\n# SOP\nCheck requirements first.'


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config,'WORKSPACE_DIR',tmp_path/'workspace')
    monkeypatch.setattr(config,'TEMP_DIR',tmp_path/'temp')


def archive(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as bundle:
        for name,data in files: bundle.writestr(name,data)
    return stream.getvalue()


def test_upload_md_zip_list_isolation_and_uninstall():
    result=asyncio.run(service.upload('general','SKILL.md',SKILL))
    assert result['id']=='department-sop' and result['source']==''
    assert service.installed('general')[0]['name']=='department-sop'
    assert service.installed('product')==[]
    with pytest.raises(service.SkillError,match='同名'):
        asyncio.run(service.upload('general','SKILL.md',SKILL))
    asyncio.run(service.uninstall('general',result['id']))
    result=asyncio.run(service.upload('general','sop.zip',archive([('sop/SKILL.md',SKILL),('sop/scripts/run.py',b'print(123)')])))
    assert (service.skill_directory('general')/'department-sop/scripts/run.py').is_file()
    assert result['id']=='department-sop'


@pytest.mark.parametrize('files',[[('SKILL.md',SKILL),('../bad',b'bad')],[('SKILL.md',SKILL),('C:/bad',b'bad')],[('a/SKILL.md',SKILL),('b/SKILL.md',SKILL)]])
def test_unsafe_or_ambiguous_zip_is_not_installed(files):
    with pytest.raises(service.SkillError):
        asyncio.run(service.upload('general','sop.zip',archive(files)))
    assert service.installed('general')==[]
