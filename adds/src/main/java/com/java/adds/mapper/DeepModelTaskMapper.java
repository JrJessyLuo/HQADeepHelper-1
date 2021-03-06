package com.java.adds.mapper;


import com.java.adds.entity.DeepModelTaskEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.springframework.data.relational.core.sql.In;
import org.springframework.stereotype.Repository;

import java.util.ArrayList;

@Mapper
@Repository
public interface DeepModelTaskMapper {
    /**ljy
     * 医生运行一个深度学习模型
     * @return
     */
    //public Long doDeepModelTask(@Param("userId") Long doctorId, @Param("taskName")String taskName,@Param("datasetId") Long datasetId,@Param("qLen") Integer qLen,@Param("dLen")Integer dLen,@Param("modelId") Long modelId,@Param("metricId") Long metricId,@Param("status")Integer status);
    public Long doDeepModelTask(DeepModelTaskEntity deepModelTaskEntity);
    /**ljy
     * 查找是否有已经有相同的模型运行结果
     * @return
     */
    public ArrayList<DeepModelTaskEntity> getSimilarityModelTask(@Param("datasetId") Long datasetId,@Param("qLen") Integer qlen,@Param("dLen")Integer dLen,@Param("modelId") Long modelId);

    /**ljy
     * 更新模型运行结果
     * @return
     */
    public void updateTask(@Param("id") Long taskId,@Param("status") Integer status,@Param("result") Long result);

    /**
     * 医生获取所有任务
     * @author ljy
     * @return
     */
    public ArrayList<DeepModelTaskEntity> getDMTasks(@Param("userId") Integer doctorId);


}
